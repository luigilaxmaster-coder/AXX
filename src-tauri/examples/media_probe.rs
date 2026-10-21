//! Test harness for the same native media service used by Tauri (JSON lines).
#[path = "../src/system_media.rs"]
#[allow(dead_code)]
mod system_media;
use std::io::{self, BufRead, Write};
fn main() {
    for line in io::stdin().lock().lines().map_while(Result::ok) {
        let request: serde_json::Value = serde_json::from_str(&line).unwrap_or_default();
        let result = if let Some(command) = request["command"].as_str() {
            match system_media::control(
                request["id"].as_str().unwrap_or_default().into(),
                command.into(),
                request["value"].as_f64(),
            ) {
                Ok(ok) => serde_json::json!({"ok":ok}),
                Err(error) => serde_json::json!({"error":error}),
            }
        } else {
            system_media::system_media_status()
        };
        println!("{}", result);
        let _ = io::stdout().flush();
    }
}
