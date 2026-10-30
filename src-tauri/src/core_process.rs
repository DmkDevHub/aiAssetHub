use serde_json::{Value, json};
use std::io::{BufRead, BufReader, Read, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{self, Receiver};
use std::thread::{self, JoinHandle};
use std::time::Duration;

const MAX_FRAME: usize = 16_384;
const TIMEOUT: Duration = Duration::from_secs(3);

pub fn data_location(development: bool, app_data: PathBuf) -> (PathBuf, &'static str) {
    if development {
        (
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.artifacts/data/development"),
            "development",
        )
    } else {
        (app_data.join("data"), "production")
    }
}

#[derive(Clone)]
pub struct LaunchSpec {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub cwd: PathBuf,
}

impl LaunchSpec {
    pub fn packaged(directory: PathBuf) -> Self {
        Self {
            program: directory.join("ai-asset-hub-core.exe"),
            args: vec!["--serve".into()],
            cwd: directory,
        }
    }

    pub fn with_data(mut self, directory: PathBuf, environment: &str) -> Self {
        self.args.extend([
            "--data-dir".into(),
            directory.to_string_lossy().into_owned(),
            "--environment".into(),
            environment.into(),
        ]);
        self
    }

    pub fn development() -> Self {
        let packages = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../.artifacts/core-build-venv/Lib/site-packages");
        let args = if packages.is_dir() {
            vec![
                "-B".into(),
                "-c".into(),
                format!(
                    "import site,runpy;site.addsitedir({});runpy.run_module('ai_asset_hub_core',run_name='__main__')",
                    serde_json::to_string(&packages.to_string_lossy()).unwrap()
                ),
                "--serve".into(),
            ]
        } else {
            vec![
                "-B".into(),
                "-m".into(),
                "ai_asset_hub_core".into(),
                "--serve".into(),
            ]
        };
        Self {
            program: std::env::var_os("AI_ASSET_HUB_PYTHON")
                .unwrap_or_else(|| "python".into())
                .into(),
            args,
            cwd: PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../python-core"),
        }
    }
}

struct Session {
    child: Child,
    stdin: Option<ChildStdin>,
    responses: Receiver<Result<Vec<u8>, ()>>,
    reader: Option<JoinHandle<()>>,
}

impl Session {
    fn stop(&mut self) {
        self.stdin.take();
        // EOF is normal shutdown. Bound the grace period, then reap a stuck child.
        for _ in 0..20 {
            if matches!(self.child.try_wait(), Ok(Some(_))) {
                break;
            }
            thread::sleep(Duration::from_millis(10));
        }
        if !matches!(self.child.try_wait(), Ok(Some(_))) {
            let _ = self.child.kill();
        }
        let _ = self.child.wait();
        if let Some(reader) = self.reader.take() {
            let _ = reader.join();
        }
    }
}

impl Drop for Session {
    fn drop(&mut self) {
        self.stop();
    }
}

pub struct CoreProcess {
    spec: LaunchSpec,
    session: Option<Session>,
    last_error: Option<&'static str>,
    timeout: Duration,
}

impl CoreProcess {
    pub fn new(spec: LaunchSpec) -> Self {
        Self {
            spec,
            session: None,
            last_error: None,
            timeout: TIMEOUT,
        }
    }

    pub fn start(&mut self) -> Result<Value, &'static str> {
        let result = self.launch();
        if let Err(code) = result {
            self.last_error = Some(code);
            self.stop();
        }
        result
    }

    fn launch(&mut self) -> Result<Value, &'static str> {
        self.stop();
        self.last_error = None;
        let mut command = Command::new(&self.spec.program);
        command
            .args(&self.spec.args)
            .current_dir(&self.spec.cwd)
            .env("PYTHONUTF8", "1")
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        command.env_remove("PYTHONHOME").env_remove("PYTHONPATH");
        if self
            .spec
            .program
            .file_name()
            .is_some_and(|name| name == "ai-asset-hub-core.exe")
            && let Some(windows) = std::env::var_os("SystemRoot")
        {
            command.env("PATH", PathBuf::from(windows).join("System32"));
        }
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000); // CREATE_NO_WINDOW
        }
        let mut child = command.spawn().map_err(|_| "CORE_START_FAILED")?;
        let stdin = child.stdin.take();
        let stdout = child.stdout.take().ok_or("CORE_START_FAILED")?;
        let (sender, responses) = mpsc::sync_channel(1);
        let reader = thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            loop {
                let mut frame = Vec::new();
                let read = (&mut reader)
                    .take((MAX_FRAME + 1) as u64)
                    .read_until(b'\n', &mut frame);
                let valid =
                    matches!(read, Ok(n) if n > 0 && n <= MAX_FRAME) && frame.ends_with(b"\n");
                if !valid {
                    let _ = sender.try_send(Err(()));
                    break;
                }
                if sender.try_send(Ok(frame)).is_err() {
                    break;
                }
            }
        });
        self.session = Some(Session {
            child,
            stdin,
            responses,
            reader: Some(reader),
        });
        self.health()
    }

    pub fn health(&mut self) -> Result<Value, &'static str> {
        let result = self.exchange("health.get", json!({})).and_then(|response| {
            let pid = self
                .session
                .as_ref()
                .map(|session| session.child.id() as u64);
            if response["ok"] != true
                || response["data"]["core"]["pid"].as_u64() != pid
                || response["data"]["core"]["status"] != "ready"
                || response["data"]["core"]["version"].as_str() != Some(env!("CARGO_PKG_VERSION"))
                || response["data"]["core"]["uptime_ms"].as_u64().is_none()
            {
                return Err("CORE_PROTOCOL_ERROR");
            }
            Ok(response)
        });
        if let Err(code) = result {
            self.last_error = Some(code);
            self.stop();
        } else {
            self.last_error = None;
        }
        result
    }

    pub fn library_request(&mut self, method: &str, params: Value) -> Result<Value, &'static str> {
        if !matches!(
            method,
            "library.register"
                | "library.unregister"
                | "library.list"
                | "library.scan"
                | "asset.list"
                | "asset.thumbnail"
                | "asset.get"
                | "asset.management"
                | "asset.management.save"
                | "asset.technical"
                | "analysis.review"
                | "analysis.review.apply"
                | "asset.technical.collect"
                | "asset.composition"
                | "asset.composition.save"
                | "asset.link.candidates"
                | "asset.relations"
                | "asset.relations.save"
                | "asset.metadata.history"
                | "asset.groups.list"
                | "asset.groups.create"
                | "asset.groups.update"
                | "asset.groups.delete"
                | "asset.groups.membership"
                | "asset.groups.assign"
                | "asset.groups.move"
                | "asset.groups.query"
                | "asset.groups.batch_preview"
                | "asset.groups.batch_apply"
                | "asset.packages.list"
                | "asset.packages.create"
                | "asset.packages.update"
                | "asset.packages.delete"
                | "asset.packages.membership"
                | "asset.packages.assign"
                | "asset.packages.defaults"
                | "asset.packages.effective"
                | "asset.packages.override"
                | "license.list"
                | "license.get"
                | "license.create"
                | "license.update"
                | "license.delete"
                | "license.evidence.save"
                | "creator.delete.preview"
                | "creator.delete"
                | "source.delete.preview"
                | "license.delete.preview"
                | "provenance.history"
                | "provenance.export"
                | "catalog.classification"
                | "catalog.classification.save"
                | "catalog.evidence_candidates"
                | "catalog.term.get"
                | "catalog.term.save"
                | "catalog.tag.get"
                | "catalog.tag.save"
                | "catalog.tag.delete"
                | "catalog.order"
                | "catalog.query"
                | "catalog.options"
                | "catalog.scope"
                | "source.list"
                | "source.get"
                | "source.create"
                | "source.update"
                | "source.delete"
                | "creator.links"
                | "creator.links.save"
                | "creator.list"
                | "creator.get"
                | "creator.create"
                | "creator.update"
                | "creator.set_enabled"
                | "asset.annotations"
                | "asset.tags"
                | "asset.annotate"
                | "asset.tags.batch"
                | "asset.search"
                | "model.register"
                | "model.list"
                | "model.inspect"
                | "model.credential"
                | "model.policy"
                | "model.validate"
                | "model.select"
                | "analysis.preview"
                | "analysis.start"
                | "analysis.status"
                | "analysis.jobs"
                | "embedding.configure"
                | "embedding.status"
                | "embedding.start"
                | "embedding.work"
                | "embedding.query"
                | "embedding.rebuild"
                | "mcp.audit"
                | "mcp.connection"
                | "analysis.cancel"
                | "analysis.retry_plan"
                | "asset.analysis"
                | "asset.analysis.history"
        ) {
            return Err("CORE_COMMAND_NOT_ALLOWED");
        }
        let result = self.exchange(method, params);
        if let Err(code) = result
            && code != "CORE_REQUEST_TOO_LARGE"
        {
            self.last_error = Some(code);
            self.stop();
        }
        result
    }

    fn exchange(&mut self, method: &str, params: Value) -> Result<Value, &'static str> {
        let session = self
            .session
            .as_mut()
            .ok_or(self.last_error.unwrap_or("CORE_UNAVAILABLE"))?;
        if session
            .child
            .try_wait()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .is_some()
        {
            return Err("CORE_EXITED");
        }
        let id = uuid::Uuid::new_v4().to_string();
        let request =
            json!({"request_id": id, "method": method, "params": params}).to_string() + "\n";
        if request.len() > MAX_FRAME {
            return Err("CORE_REQUEST_TOO_LARGE");
        }
        let stdin = session.stdin.as_mut().ok_or("CORE_UNAVAILABLE")?;
        stdin
            .write_all(request.as_bytes())
            .map_err(|_| "CORE_UNAVAILABLE")?;
        stdin.flush().map_err(|_| "CORE_UNAVAILABLE")?;
        let bytes = session
            .responses
            .recv_timeout(self.timeout)
            .map_err(|_| "CORE_TIMEOUT")?
            .map_err(|_| "CORE_PROTOCOL_ERROR")?;
        let response: Value = serde_json::from_slice(&bytes).map_err(|_| "CORE_PROTOCOL_ERROR")?;
        if response["request_id"] != id
            || !response["ok"].is_boolean()
            || (response["ok"] == true
                && (!response["error"].is_null() || !response["data"].is_object()))
            || (response["ok"] == false
                && (!response["data"].is_null() || response["error"]["code"].as_str().is_none()))
        {
            return Err("CORE_PROTOCOL_ERROR");
        }
        Ok(response)
    }

    pub fn stop(&mut self) {
        self.session.take();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn latest_schema_version() -> usize {
        std::fs::read_dir(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../db/migrations"))
            .unwrap()
            .filter_map(Result::ok)
            .filter(|entry| entry.path().extension().is_some_and(|e| e == "sql"))
            .count()
    }

    fn verify_creator_dictionary(core: &mut CoreProcess) {
        let mut value = json!({"name":"제작 주체", "kind":"company", "brand":"fixture brand",
            "homepageUrl":"https://example.com", "profileUrl":"", "contact":"private@example.com",
            "country":"대한민국", "description":"fixture"});
        let created = core
            .library_request("creator.create", json!({"value":value}))
            .unwrap();
        assert_eq!(created["ok"], true);
        let id = created["data"]["id"].as_str().unwrap().to_owned();
        assert!(uuid::Uuid::parse_str(&id).is_ok());
        let listed = core
            .library_request(
                "creator.list",
                json!({"after_id":null,"include_disabled":false}),
            )
            .unwrap();
        assert_eq!(listed["data"]["items"][0]["id"], id);
        assert!(listed["data"]["items"][0].get("contact").is_none());
        value["name"] = json!("수정된 제작 주체");
        let updated = core
            .library_request(
                "creator.update",
                json!({"creator_id":id,"value":value,"expected_revision":1}),
            )
            .unwrap();
        assert_eq!(updated["data"]["revision"], 2);
        let stale = core
            .library_request(
                "creator.update",
                json!({"creator_id":id,"value":value,"expected_revision":1}),
            )
            .unwrap();
        assert_eq!(stale["error"]["code"], "METADATA_CONFLICT");
        let disabled = core
            .library_request(
                "creator.set_enabled",
                json!({"creator_id":id,"enabled":false,"expected_revision":2}),
            )
            .unwrap();
        assert_eq!(disabled["data"]["enabled"], false);
        core.stop();
        core.start().unwrap();
        let restored = core
            .library_request("creator.get", json!({"creator_id":id}))
            .unwrap();
        assert_eq!(restored["data"], disabled["data"]);
        let jobs = core.library_request("analysis.jobs", json!({})).unwrap();
        assert_eq!(jobs["data"]["items"], json!([]));
    }

    fn verify_provenance_contract(core: &mut CoreProcess, asset_id: &str) {
        let subject = json!({"kind":"asset","id":asset_id});
        let creator = core.library_request("creator.create", json!({"value":{"name":"fixture rights creator","kind":"person","brand":"","homepageUrl":"","profileUrl":"","contact":"private-fixture-contact","country":"","description":""}})).unwrap();
        assert_eq!(creator["ok"], true);
        assert!(!creator.to_string().contains("private-fixture-contact"));
        let creator_id = creator["data"]["id"].as_str().unwrap().to_owned();
        let links = core.library_request("creator.links.save", json!({"subject":subject,"links":[{"creator_id":creator_id,"role":"creator"}],"expected_revision":0})).unwrap();
        assert_eq!(links["data"]["revision"], 1);
        let found = core.library_request("catalog.query", json!({"query":"fixture rights creator","criteria":{"creator_ids":[creator_id],"creator_roles":["creator"]},"sort":"creator","after_id":null})).unwrap();
        assert_eq!(found["ok"], true);
        assert_eq!(found["data"]["ids"], json!([asset_id]));
        assert_eq!(found["data"]["inferenceCalled"], false);
        let private_search = core
            .library_request(
                "catalog.query",
                json!({"query":"private-fixture-contact","criteria":{},"after_id":null}),
            )
            .unwrap();
        assert_eq!(private_search["data"]["ids"], json!([]));
        let ordered = core
            .library_request(
                "catalog.order",
                json!({"asset_ids":[asset_id],"sort":"size_desc"}),
            )
            .unwrap();
        assert_eq!(ordered["data"]["ids"], json!([asset_id]));
        let classification = core
            .library_request("catalog.classification", json!({"asset_id":asset_id}))
            .unwrap();
        assert_eq!(classification["ok"], true);
        let source = core.library_request("source.create", json!({"subject":subject,"value":{"site":"fixture","productName":"declared","originalUrl":"","productUrl":"","downloadUrl":"https://example.com/?key=private-fixture-url","purchase":{"amount":"0","currency":"KRW","purchasedOn":"2024-02-29","downloadedOn":""}}})).unwrap();
        assert_eq!(source["ok"], true);
        let source_id = source["data"]["id"].as_str().unwrap().to_owned();
        let license = core.library_request("license.create", json!({"subject":subject,"confirmed":true,"value":{"label":"fixture declared license","terms":"private-fixture-terms","attribution":"credit","reviewStatus":"user_reviewed","scope":"fixture asset","note":"private-fixture-note","source_id":source_id}})).unwrap();
        assert_eq!(license["data"]["permission"], "unknown");
        let license_id = license["data"]["id"].as_str().unwrap().to_owned();
        let files = core
            .library_request("asset.composition", json!({"asset_id":asset_id}))
            .unwrap();
        let file_id = files["data"]["value"]["files"][0]["fileId"]
            .as_str()
            .unwrap();
        let evidence = core.library_request("license.evidence.save", json!({"record_id":license_id,"files":[{"file_id":file_id,"label":"private-fixture-proof"}],"expected_revision":1,"confirmed":true})).unwrap();
        assert_eq!(evidence["data"]["evidenceCount"], 1);
        for kind in ["creators", "sources", "licenses"] {
            let export = core
                .library_request(
                    "provenance.export",
                    json!({"subject":subject,"kind":kind,"after_id":null}),
                )
                .unwrap();
            assert_eq!(export["ok"], true);
            assert!(!export.to_string().contains("private-fixture"));
        }
        let history = core
            .library_request(
                "provenance.history",
                json!({"subject":subject,"after_id":null}),
            )
            .unwrap();
        assert_eq!(history["ok"], true);
        assert!(!history.to_string().contains("private-fixture"));
        let private = core
            .library_request(
                "source.get",
                json!({"record_id":source_id,"include_private":true}),
            )
            .unwrap();
        assert_eq!(private["error"]["code"], "INVALID_PARAMS");
        core.stop();
        core.start().unwrap();
        let restored = core
            .library_request("license.get", json!({"record_id":license_id}))
            .unwrap();
        assert_eq!(restored["data"], evidence["data"]);
        let blocked = core
            .library_request(
                "source.delete",
                json!({"record_id":source_id,"expected_revision":1,"confirmed":true}),
            )
            .unwrap();
        assert_eq!(blocked["error"]["code"], "METADATA_CONFLICT");
        let preview = core
            .library_request("source.delete.preview", json!({"record_id":source_id}))
            .unwrap();
        assert_eq!(preview["data"]["references"], 1);
        let deleted = core.library_request("source.delete", json!({"record_id":source_id,"expected_revision":1,"expected_references":1,"confirmed":true})).unwrap();
        assert_eq!(deleted["data"]["enabled"], false);
        let deleted = core.library_request("license.delete", json!({"record_id":license_id,"expected_revision":2,"expected_references":1,"confirmed":true})).unwrap();
        assert_eq!(deleted["data"]["enabled"], false);
        let plan = core
            .library_request("creator.delete.preview", json!({"creator_id":creator_id}))
            .unwrap();
        assert_eq!(plan["data"]["canDelete"], false);
        core.library_request(
            "creator.links.save",
            json!({"subject":subject,"links":[],"expected_revision":1}),
        )
        .unwrap();
        let plan = core
            .library_request("creator.delete.preview", json!({"creator_id":creator_id}))
            .unwrap();
        let deleted = core
            .library_request(
                "creator.delete",
                json!({"plan":plan["data"],"confirmed":true}),
            )
            .unwrap();
        assert_eq!(deleted["data"]["deleted"], true);
        assert_eq!(
            core.library_request("analysis.jobs", json!({})).unwrap()["data"]["items"],
            json!([])
        );
    }

    #[test]
    fn provenance_privacy_references_and_history_survive_real_core_restart() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../.artifacts/provenance-wire-tests")
            .join(uuid::Uuid::new_v4().to_string());
        let source = root.join("source");
        std::fs::create_dir_all(&source).unwrap();
        std::fs::write(source.join("evidence.txt"), b"fixture evidence").unwrap();
        let path = source
            .canonicalize()
            .unwrap()
            .to_string_lossy()
            .trim_start_matches(r"\\?\")
            .to_owned();
        let mut core =
            CoreProcess::new(LaunchSpec::development().with_data(root.join("data"), "development"));
        core.start().unwrap();
        let library = core
            .library_request("library.register", json!({"path":path}))
            .unwrap();
        assert_eq!(library["ok"], true);
        core.library_request(
            "library.scan",
            json!({"library_id":library["data"]["library"]["id"]}),
        )
        .unwrap();
        let listed = core.library_request("asset.list", json!({})).unwrap();
        let id = listed["data"]["items"][0]["id"].as_str().unwrap();
        verify_provenance_contract(&mut core, id);
        assert_eq!(
            std::fs::read(source.join("evidence.txt")).unwrap(),
            b"fixture evidence"
        );
    }

    #[test]
    fn creator_dictionary_survives_restart_without_starting_analysis() {
        let data = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../.artifacts/creator-wire-tests")
            .join(uuid::Uuid::new_v4().to_string());
        let mut core = CoreProcess::new(LaunchSpec::development().with_data(data, "development"));
        core.start().unwrap();
        verify_creator_dictionary(&mut core);
    }

    fn verify_model_registry(core: &mut CoreProcess) {
        let connection = core.library_request("mcp.connection", json!({})).unwrap();
        assert_eq!(connection["data"]["brokerReady"], true);
        assert_eq!(connection["data"]["readOnly"], true);
        let audit = core.library_request("mcp.audit", json!({})).unwrap();
        assert_eq!(audit["data"]["items"], json!([]));
        let embedding = core.library_request("embedding.status", json!({})).unwrap();
        assert_eq!(embedding["ok"], true);
        assert!(embedding["data"]["profile"].is_null());
        assert_eq!(embedding["data"]["readyCount"], 0);
        let unapproved = core
            .library_request("embedding.rebuild", json!({"confirmed":false}))
            .unwrap();
        assert_eq!(unapproved["error"]["code"], "INVALID_PARAMS");
        let registered=core.library_request("model.register",json!({"provider_name":"Ollama","kind":"local","model_id":"fixture-model:wire-test","modalities":["image"]})).unwrap();
        assert_eq!(registered["ok"], true);
        let identifier = registered["data"]["id"].as_str().unwrap();
        assert!(uuid::Uuid::parse_str(identifier).is_ok());
        let listed = core.library_request("model.list", json!({})).unwrap();
        assert_eq!(listed["data"]["items"][0]["id"], identifier);
        assert_eq!(listed["data"]["items"][0]["enabled"], false);
        let validated = core
            .library_request(
                "model.validate",
                json!({"id":identifier,"modality":"image"}),
            )
            .unwrap();
        assert_eq!(validated["data"]["compatible"], false);
        assert_eq!(validated["data"]["reason"], "MODEL_UNAVAILABLE");
    }

    #[test]
    fn real_pipe_health_reuses_process_and_stops_on_eof() {
        let mut core = CoreProcess::new(LaunchSpec::development());
        let first = core.start().unwrap();
        let second = core.health().unwrap();
        assert_eq!(first["data"]["core"]["pid"], second["data"]["core"]["pid"]);
        assert_ne!(first["request_id"], second["request_id"]);
        core.stop();
        assert!(core.session.is_none());
        assert_eq!(core.health().unwrap_err(), "CORE_UNAVAILABLE");
        assert!(core.start().is_ok());
    }

    #[test]
    fn missing_executable_is_a_redacted_start_error() {
        let mut spec = LaunchSpec::development();
        spec.program = PathBuf::from("fixture-missing-private-program");
        let mut core = CoreProcess::new(spec);
        assert_eq!(core.start().unwrap_err(), "CORE_START_FAILED");
        assert!(core.session.is_none());
        assert_eq!(core.health().unwrap_err(), "CORE_START_FAILED");
    }

    #[test]
    #[ignore = "requires a built or installed Sidecar; set AI_ASSET_HUB_SIDECAR_DIR"]
    fn packaged_core_needs_no_python_or_development_path() {
        let directory = PathBuf::from(
            std::env::var_os("AI_ASSET_HUB_SIDECAR_DIR").expect("Sidecar directory required"),
        );
        let data = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../.artifacts/packaged-data")
            .join(uuid::Uuid::new_v4().to_string());
        let mut core =
            CoreProcess::new(LaunchSpec::packaged(directory).with_data(data.clone(), "production"));
        let first = core.start().unwrap();
        assert_eq!(first["data"]["database"]["status"], "ready");
        assert_eq!(
            first["data"]["database"]["schema_version"],
            latest_schema_version()
        );
        verify_model_registry(&mut core);
        verify_creator_dictionary(&mut core);
        let source = data
            .parent()
            .unwrap()
            .join(format!("image-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&source).unwrap();
        let hex = "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c49444154789c63f8cfc0000003010100c9fe92ef0000000049454e44ae426082";
        let png: Vec<u8> = (0..hex.len())
            .step_by(2)
            .map(|index| u8::from_str_radix(&hex[index..index + 2], 16).unwrap())
            .collect();
        std::fs::write(source.join("fixture.png"), &png).unwrap();
        let path = source
            .canonicalize()
            .unwrap()
            .to_string_lossy()
            .trim_start_matches(r"\\?\")
            .to_owned();
        let registered = core
            .library_request("library.register", json!({"path":path}))
            .unwrap();
        let library = registered["data"]["library"]["id"].as_str().unwrap();
        assert_eq!(
            core.library_request("library.scan", json!({"library_id":library}))
                .unwrap()["data"]["processed"],
            1
        );
        let listed = core.library_request("asset.list", json!({})).unwrap();
        let id = listed["data"]["items"][0]["id"].as_str().unwrap();
        let preview = core
            .library_request("asset.thumbnail", json!({"asset_id":id}))
            .unwrap();
        assert_eq!(preview["data"]["status"], "ready");
        assert_eq!(preview["data"]["width"], 1);
        assert_eq!(
            core.library_request(
                "asset.tags",
                json!({"asset_id":id,"add":["한글숲"],"remove":[]})
            )
            .unwrap()["ok"],
            true
        );
        assert_eq!(
            core.library_request(
                "asset.annotate",
                json!({"asset_id":id,"title":"나무","description":"산속의 푸른 나무","aliases":["Tree","숲 나무"],"expected_revision":0})
            )
            .unwrap()["ok"],
            true
        );
        assert_eq!(
            core.library_request("asset.search", json!({"query":"푸른 숲"}))
                .unwrap()["data"]["ids"],
            json!([id])
        );

        assert_eq!(std::fs::read(source.join("fixture.png")).unwrap(), png);
        let saved = core
            .library_request("asset.annotations", json!({"asset_id":id}))
            .unwrap();
        assert_eq!(saved["data"]["aliases"], json!(["Tree", "숲 나무"]));
        assert_eq!(saved["data"]["originalName"], "fixture.png");
        let management = json!({"favorite":true,"rating":5,"status":"approved","notes":"한글 메모","assetVersion":"v1","createdDate":"2024-02-29","modifiedDate":"2026-10-29"});
        let managed = core
            .library_request(
                "asset.management.save",
                json!({"asset_id":id,"value":management,"expected_revision":0}),
            )
            .unwrap();
        assert_eq!(managed["data"]["revision"], 1);
        let composition = core
            .library_request("asset.composition", json!({"asset_id":id}))
            .unwrap();
        assert_eq!(composition["data"]["availability"], "available");
        assert_eq!(
            core.library_request(
                "asset.composition.save",
                json!({"asset_id":id,"value":composition["data"]["value"],"expected_revision":0})
            )
            .unwrap()["ok"],
            true
        );
        assert_eq!(
            core.library_request(
                "asset.relations.save",
                json!({"asset_id":id,"value":[],"expected_revision":0})
            )
            .unwrap()["ok"],
            true
        );
        assert_eq!(
            core.library_request(
                "asset.link.candidates",
                json!({"asset_id":id,"kind":"file","after_id":null})
            )
            .unwrap()["data"]["items"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        let history = core
            .library_request(
                "asset.metadata.history",
                json!({"asset_id":id,"before_id":null}),
            )
            .unwrap();
        assert_eq!(history["data"]["items"][0]["field"], "relations");
        let group = core
            .library_request(
                "asset.groups.create",
                json!({"value":{"name":"fixture group","description":"logical"}}),
            )
            .unwrap();
        let group_id = group["data"]["id"].as_str().unwrap();
        let child = core
            .library_request(
                "asset.groups.create",
                json!({"value":{"name":"child","description":""}}),
            )
            .unwrap();
        let child_id = child["data"]["id"].as_str().unwrap();
        assert_eq!(
            core.library_request(
                "asset.groups.move",
                json!({"group_id":child_id,"parent_id":group_id,"expected_revision":1})
            )
            .unwrap()["ok"],
            true
        );
        assert_eq!(
            core.library_request(
                "asset.groups.assign",
                json!({"asset_id":id,"group_ids":[group_id],"expected_revision":0})
            )
            .unwrap()["ok"],
            true
        );
        assert_eq!(
            core.library_request(
                "asset.groups.query",
                json!({"group_id":group_id,"query":"","criteria":{},"after_id":null})
            )
            .unwrap()["data"]["ids"],
            json!([id])
        );
        let plan = core
            .library_request(
                "asset.groups.batch_preview",
                json!({"asset_ids":[id],"add":[child_id],"remove":[],"after_id":null}),
            )
            .unwrap();
        assert_eq!(
            core.library_request(
                "asset.groups.batch_apply",
                json!({"plan":plan["data"]["plan"],"confirmed":true})
            )
            .unwrap()["data"]["updated"],
            1
        );
        let package = core.library_request("asset.packages.create", json!({"value":{"name":"fixture package","description":"declared","unit":"distribution","version":"v1","purchase":{"amount":null,"currency":"","date":""}}})).unwrap();
        let package_id = package["data"]["id"].as_str().unwrap();
        assert_eq!(
            core.library_request(
                "asset.packages.defaults",
                json!({"package_id":package_id,"value":{"engine":"Unity"},"expected_revision":1})
            )
            .unwrap()["ok"],
            true
        );
        assert_eq!(
            core.library_request(
                "asset.packages.assign",
                json!({"asset_id":id,"package_ids":[package_id],"expected_revision":0})
            )
            .unwrap()["ok"],
            true
        );
        let inherited = core
            .library_request("asset.packages.effective", json!({"asset_id":id}))
            .unwrap();
        assert_eq!(inherited["data"]["fields"]["engine"]["value"], "Unity");
        let overridden = core.library_request("asset.packages.override", json!({"asset_id":id,"value":{"engine":"Godot"},"expected_revision":0,"expected_packages":inherited["data"]["packageVersions"]})).unwrap();
        assert_eq!(overridden["data"]["fields"]["engine"]["value"], "Godot");
        let conflict = core.library_request("asset.annotate", json!({"asset_id":id,"title":"stale","description":"","aliases":[],"expected_revision":0})).unwrap();
        assert_eq!(conflict["error"]["code"], "METADATA_CONFLICT");
        core.stop();
        let next = core.start().unwrap();
        assert_eq!(next["data"]["database"]["status"], "ready");
        assert_ne!(first["data"]["core"]["pid"], next["data"]["core"]["pid"]);
        let reopened = core
            .library_request("asset.annotations", json!({"asset_id":id}))
            .unwrap();
        assert_eq!(reopened["data"], saved["data"]);
        assert_eq!(
            core.library_request("asset.groups.membership", json!({"asset_id":id}))
                .unwrap()["data"]["ids"]
                .as_array()
                .unwrap()
                .len(),
            2
        );
        assert_eq!(
            core.library_request("asset.packages.effective", json!({"asset_id":id}))
                .unwrap()["data"],
            overridden["data"]
        );

        assert_eq!(
            core.library_request("asset.management", json!({"asset_id":id}))
                .unwrap()["data"],
            managed["data"]
        );
        assert_eq!(
            core.library_request("asset.composition", json!({"asset_id":id}))
                .unwrap()["data"]["value"],
            composition["data"]["value"]
        );
        verify_provenance_contract(&mut core, id);
    }

    #[test]
    fn data_locations_are_separate_and_database_survives_restart() {
        let app_data = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../.artifacts/native-tests")
            .join(uuid::Uuid::new_v4().to_string());
        let (dev, _) = data_location(true, app_data.clone());
        let (prod, environment) = data_location(false, app_data);
        assert_ne!(dev, prod);
        assert_eq!(environment, "production");
        let mut core =
            CoreProcess::new(LaunchSpec::development().with_data(prod.clone(), environment));
        let health = core.start().unwrap();
        assert_eq!(health["data"]["database"]["status"], "ready");
        assert_eq!(
            health["data"]["database"]["schema_version"],
            latest_schema_version()
        );
        core.stop();
        assert!(prod.join("asset_hub.sqlite").is_file());
        assert_eq!(core.start().unwrap()["data"]["database"]["status"], "ready");
    }

    #[test]
    fn crashed_core_releases_database_and_requires_explicit_restart() {
        let data = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../.artifacts/crash-tests")
            .join(uuid::Uuid::new_v4().to_string());
        let mut core = CoreProcess::new(LaunchSpec::development().with_data(data, "development"));
        let before = core.start().unwrap();
        let session = core.session.as_mut().unwrap();
        session.child.kill().unwrap();
        session.child.wait().unwrap();
        assert_eq!(core.health().unwrap_err(), "CORE_EXITED");
        assert!(core.session.is_none());
        assert_eq!(core.health().unwrap_err(), "CORE_EXITED");
        let after = core.start().unwrap();
        assert_ne!(before["data"]["core"]["pid"], after["data"]["core"]["pid"]);
        assert_eq!(after["data"]["database"]["status"], "ready");
    }

    #[test]
    fn timeout_kills_and_reaps_a_stalled_child_without_leaking_arguments() {
        let mut spec = LaunchSpec::development();
        spec.args = vec![
            "-B".into(),
            "-c".into(),
            "import time; time.sleep(10) # fixture-private-key".into(),
        ];
        let mut core = CoreProcess::new(spec);
        core.timeout = Duration::from_millis(100);
        let start = std::time::Instant::now();
        assert_eq!(core.start().unwrap_err(), "CORE_TIMEOUT");
        assert!(start.elapsed() < Duration::from_secs(2));
        assert!(core.session.is_none());
        assert_eq!(core.health().unwrap_err(), "CORE_TIMEOUT");
    }

    #[test]
    fn invalid_or_mismatched_frames_are_rejected_and_session_is_reaped() {
        for body in [
            "print('fixture-private-invalid-json', flush=True)",
            "print('{\"request_id\":\"wrong\",\"ok\":true}', flush=True)",
            "print('x' * 20000, flush=True)",
        ] {
            let mut spec = LaunchSpec::development();
            spec.args = vec![
                "-B".into(),
                "-c".into(),
                format!("import sys,time; sys.stdin.readline(); {body}; time.sleep(10)"),
            ];
            let mut core = CoreProcess::new(spec);
            assert_eq!(core.start().unwrap_err(), "CORE_PROTOCOL_ERROR");
            assert!(core.session.is_none());
        }
    }

    #[test]
    fn library_writes_survive_process_restart_and_business_errors_preserve_connection() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../.artifacts/library-wire-tests")
            .join(uuid::Uuid::new_v4().to_string());
        let original = root.join("원본 폴더");
        std::fs::create_dir_all(original.join("nested")).unwrap();
        std::fs::write(original.join("fixture.txt"), "fixture unchanged").unwrap();
        let path = original
            .canonicalize()
            .unwrap()
            .to_string_lossy()
            .trim_start_matches(r"\\?\")
            .to_owned();
        let mut core =
            CoreProcess::new(LaunchSpec::development().with_data(root.join("data"), "development"));
        let health = core.start().unwrap();
        verify_model_registry(&mut core);
        assert_eq!(
            core.library_request("analysis.unapproved", json!({}))
                .unwrap_err(),
            "CORE_COMMAND_NOT_ALLOWED"
        );
        assert_eq!(
            core.library_request("library.register", json!({"path": "x".repeat(MAX_FRAME)}))
                .unwrap_err(),
            "CORE_REQUEST_TOO_LARGE"
        );
        assert_eq!(
            core.health().unwrap()["data"]["core"]["pid"],
            health["data"]["core"]["pid"]
        );
        let registered = core
            .library_request("library.register", json!({"path":path}))
            .unwrap();
        assert_eq!(registered["ok"], true);
        let id = registered["data"]["library"]["id"]
            .as_str()
            .unwrap()
            .to_owned();
        let scanned = core
            .library_request("library.scan", json!({"library_id":id}))
            .unwrap();
        assert_eq!(scanned["data"]["processed"], 1);
        let listed_assets = core.library_request("asset.list", json!({})).unwrap();
        let asset_id = listed_assets["data"]["items"][0]["id"].as_str().unwrap();
        assert_eq!(
            core.library_request("asset.get", json!({"asset_id":asset_id}))
                .unwrap()["data"]["size"],
            17
        );
        assert_eq!(
            core.library_request("asset.thumbnail", json!({"asset_id":asset_id}))
                .unwrap()["data"]["status"],
            "unsupported"
        );
        assert_eq!(
            core.library_request(
                "asset.tags",
                json!({"asset_id":asset_id,"add":["숲"],"remove":[]})
            )
            .unwrap()["ok"],
            true
        );
        assert_eq!(
            core.library_request(
                "asset.annotate",
                json!({"asset_id":asset_id,"title":"별칭","description":"한글 설명"})
            )
            .unwrap()["ok"],
            true
        );
        assert_eq!(
            core.library_request(
                "asset.tags.batch",
                json!({"asset_ids":[asset_id],"add":["green"],"remove":[]})
            )
            .unwrap()["data"]["updated"],
            1
        );
        assert_eq!(
            core.library_request("asset.search", json!({"query":"설명 숲"}))
                .unwrap()["data"]["ids"],
            json!([asset_id])
        );
        assert!(uuid::Uuid::parse_str(&id).is_ok());
        let overlap = core
            .library_request(
                "library.register",
                json!({"path": format!("{path}\\nested")}),
            )
            .unwrap();
        assert_eq!(overlap["ok"], false);
        assert_eq!(overlap["error"]["code"], "LIBRARY_OVERLAP");
        assert_eq!(
            core.health().unwrap()["data"]["core"]["pid"],
            health["data"]["core"]["pid"]
        );
        core.stop();
        core.start().unwrap();
        let listed = core.library_request("library.list", json!({})).unwrap();
        assert_eq!(
            core.library_request("asset.annotations", json!({"asset_id":asset_id}))
                .unwrap()["data"]["description"],
            "한글 설명"
        );
        assert_eq!(
            core.library_request("asset.search", json!({"query":"숲"}))
                .unwrap()["data"]["ids"],
            json!([asset_id])
        );
        assert_eq!(listed["data"]["libraries"][0]["id"], id);
        assert_eq!(
            core.library_request("library.unregister", json!({"library_id":id}))
                .unwrap()["ok"],
            true
        );
        assert_eq!(
            core.library_request("library.list", json!({})).unwrap()["data"]["libraries"],
            json!([])
        );
        assert_eq!(
            std::fs::read_to_string(original.join("fixture.txt")).unwrap(),
            "fixture unchanged"
        );
    }
}
