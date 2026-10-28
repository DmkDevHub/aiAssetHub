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
        Self {
            program: std::env::var_os("AI_ASSET_HUB_PYTHON")
                .unwrap_or_else(|| "python".into())
                .into(),
            args: vec![
                "-B".into(),
                "-m".into(),
                "ai_asset_hub_core".into(),
                "--serve".into(),
            ],
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
        let result = self.exchange_health();
        if let Err(code) = result {
            self.last_error = Some(code);
            self.stop();
        } else {
            self.last_error = None;
        }
        result
    }

    fn exchange_health(&mut self) -> Result<Value, &'static str> {
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
        let request = json!({"request_id": id, "method": "health.get"}).to_string() + "\n";
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
            || response["ok"] != true
            || !response["error"].is_null()
            || response["data"]["core"]["pid"].as_u64() != Some(session.child.id() as u64)
            || response["data"]["core"]["status"] != "ready"
            || response["data"]["core"]["version"].as_str() != Some(env!("CARGO_PKG_VERSION"))
            || response["data"]["core"]["uptime_ms"].as_u64().is_none()
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
            CoreProcess::new(LaunchSpec::packaged(directory).with_data(data, "production"));
        let first = core.start().unwrap();
        assert_eq!(first["data"]["database"]["status"], "ready");
        assert_eq!(first["data"]["database"]["schema_version"], 1);
        core.stop();
        let next = core.start().unwrap();
        assert_eq!(next["data"]["database"]["status"], "ready");
        assert_ne!(first["data"]["core"]["pid"], next["data"]["core"]["pid"]);
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
        assert_eq!(health["data"]["database"]["schema_version"], 1);
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
}
