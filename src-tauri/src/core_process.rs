use serde_json::{Value, json};
use std::io::{BufRead, BufReader, Read, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{self, Receiver};
use std::thread::{self, JoinHandle};
use std::time::Duration;

const MAX_FRAME: usize = 16_384;
const TIMEOUT: Duration = Duration::from_secs(3);

#[derive(Clone)]
pub struct LaunchSpec {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub cwd: PathBuf,
}

impl LaunchSpec {
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
}

impl CoreProcess {
    pub fn new(spec: LaunchSpec) -> Self {
        Self {
            spec,
            session: None,
        }
    }

    pub fn start(&mut self) -> Result<Value, &'static str> {
        self.stop();
        let mut command = Command::new(&self.spec.program);
        command
            .args(&self.spec.args)
            .current_dir(&self.spec.cwd)
            .env("PYTHONUTF8", "1")
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
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
        if result.is_err() {
            self.stop();
        }
        result
    }

    fn exchange_health(&mut self) -> Result<Value, &'static str> {
        let session = self.session.as_mut().ok_or("CORE_UNAVAILABLE")?;
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
            .recv_timeout(TIMEOUT)
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
    }
}
