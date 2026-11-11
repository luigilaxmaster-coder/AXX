//! CPU-only, bounded PCM sidecar; the AXX supervisor kills its process tree on cancel.
use serde::Deserialize;
use serde_json::json;
use std::io::{self, BufRead, Read, Write};
use transcribe_cpp::{Backend, Model, ModelOptions, RunOptions, Session, SessionOptions, Task};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    model_path: String,
    language: Option<String>,
    task: String,
    samples: usize,
}

fn valid(request: &Request) -> bool {
    ((request.task == "prepare" && request.samples == 0)
        || (1..=60 * 16000).contains(&request.samples)
            && ["transcribe", "translate"].contains(&request.task.as_str()))
        && request.model_path.len() <= 2048
        && request
            .language
            .as_ref()
            .is_none_or(|l| (2..=3).contains(&l.len()) && l.bytes().all(|c| c.is_ascii_lowercase()))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = io::BufReader::new(io::stdin().lock());
    let mut active: Option<(String, Session)> = None;
    loop {
        let mut header = String::new();
        if input.by_ref().take(4097).read_line(&mut header)? == 0 {
            break;
        }
        if header.len() > 4096 || !header.ends_with('\n') {
            return Err("Header limit".into());
        }
        let request: Request = serde_json::from_str(&header)?;
        if !valid(&request) {
            return Err("Invalid request".into());
        }
        let mut bytes = vec![0; request.samples * 4];
        input.read_exact(&mut bytes)?;
        let audio: Vec<f32> = bytes
            .chunks_exact(4)
            .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
            .collect();
        if audio.iter().any(|s| !s.is_finite() || s.abs() > 1.01) {
            return Err("Invalid PCM".into());
        }
        drop(bytes);
        let result = (|| -> Result<_, Box<dyn std::error::Error>> {
            if !active
                .as_ref()
                .is_some_and(|(path, _)| path == &request.model_path)
            {
                active = None;
                let model = Model::load_with(
                    &request.model_path,
                    &ModelOptions {
                        backend: Backend::Cpu,
                        device: None,
                    },
                )?;
                let session = model.session_with(&SessionOptions {
                    n_threads: 2,
                    ..Default::default()
                })?;
                active = Some((request.model_path.clone(), session));
            }
            if request.task == "prepare" {
                return Ok(json!({"ok":true,"result":{"ready":true}}));
            }
            let options = RunOptions {
                language: request.language,
                task: if request.task == "translate" {
                    Task::Translate
                } else {
                    Task::Transcribe
                },
                target_language: (request.task == "translate").then(|| "en".into()),
                ..Default::default()
            };
            let result = active.as_mut().unwrap().1.run(&audio, &options)?;
            if result.text.len() > 32000 {
                return Err("Output limit".into());
            }
            Ok(json!({"ok":true,"result":{"text":result.text,"language":result.language}}))
        })()
        .unwrap_or_else(|_| {
            active = None;
            json!({"ok":false})
        });
        // ggml diagnostics may use stdout. Parent consumes bounded framed replies only.
        println!("\nAXX_ASR_V1 {result}");
        io::stdout().flush()?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bounds_pcm_and_tasks() {
        let mut r = Request {
            model_path: "model.gguf".into(),
            language: Some("es".into()),
            task: "transcribe".into(),
            samples: 16000,
        };
        assert!(valid(&r));
        r.samples = 960001;
        assert!(!valid(&r));
        r.samples = 1;
        r.task = "instruct".into();
        assert!(!valid(&r));
    }
}
