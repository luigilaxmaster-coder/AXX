//! Authenticated desktop-side streaming for the configured local Ollama model.
//! The WebView receives only text deltas; it never receives the backend token.
use super::{HostState, request_backend};
use serde_json::{Value, json};
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};

const MAX_PROMPT_BYTES: usize = 100_000;
const MAX_RESPONSE_BYTES: usize = 64_000;

fn validate_model(model: &str) -> Result<(), String> {
    if model.is_empty() || model.len() > 200 || model.chars().any(char::is_control) {
        return Err("Invalid model".into());
    }
    Ok(())
}

fn validate_messages(model: &str, messages: &[Value]) -> Result<(), String> {
    validate_model(model)?;
    if messages.is_empty() || messages.len() > 32 {
        return Err("Invalid chat history".into());
    }
    let mut size = 0;
    for message in messages {
        let role = message.get("role").and_then(Value::as_str);
        let content = message.get("content").and_then(Value::as_str);
        if !matches!(role, Some("system" | "user" | "assistant")) || content.is_none() {
            return Err("Invalid chat message".into());
        }
        size += content.unwrap().len();
        if size > MAX_PROMPT_BYTES {
            return Err("Chat history exceeds its limit".into());
        }
    }
    Ok(())
}

fn parse_line(line: &[u8]) -> Result<(String, bool, String), String> {
    let value: Value = serde_json::from_slice(line).map_err(|_| "Invalid local model stream")?;
    if value.get("error").is_some() {
        return Err("Local model stopped before completing its answer".into());
    }
    let delta = value
        .pointer("/message/content")
        .and_then(Value::as_str)
        .unwrap_or("");
    let done = value.get("done").and_then(Value::as_bool).unwrap_or(false);
    if delta.len() > 16_384 {
        return Err("Local model stream chunk exceeds its limit".into());
    }
    let reason = value
        .get("done_reason")
        .and_then(Value::as_str)
        .unwrap_or("stop");
    Ok((delta.to_string(), done, reason.to_string()))
}

async fn verify_local_model(app: &AppHandle, model: &str) -> Result<(), String> {
    let state = app.state::<HostState>();
    let connection = state
        .backend
        .lock()
        .unwrap()
        .clone()
        .ok_or("Backend is starting")?;
    let status = tauri::async_runtime::spawn_blocking(move || {
        request_backend(&connection, "GET", "/axx-api/status", None)
    })
    .await
    .map_err(|_| "Cannot check local model configuration")??;
    let eligible = status
        .pointer("/details/realtime_local_models")
        .and_then(Value::as_array)
        .is_some_and(|models| models.iter().any(|name| name.as_str() == Some(model)));
    if !eligible {
        return Err("Local Ollama model is not enabled for realtime chat".into());
    }
    Ok(())
}

fn local_client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .no_proxy()
        .connect_timeout(Duration::from_secs(3))
        .timeout(Duration::from_secs(180))
        .build()
        .map_err(|_| "Cannot initialize local model transport".into())
}

async fn stream_local(
    app: &AppHandle,
    request_id: &str,
    model: &str,
    messages: &[Value],
    cancelled: &Arc<AtomicBool>,
) -> Result<Value, String> {
    verify_local_model(app, model).await?;
    let client = local_client()?;
    let mut response = client
        .post("http://127.0.0.1:11434/api/chat")
        .json(&json!({"model": model, "messages": messages, "stream": true, "keep_alive": "30m"}))
        .send()
        .await
        .map_err(|_| "Local Ollama is unavailable")?;
    if !response.status().is_success() {
        return Err(format!(
            "Local Ollama returned HTTP {}",
            response.status().as_u16()
        ));
    }
    let mut pending = Vec::new();
    let mut answer = String::new();
    loop {
        let chunk = tokio::select! {
            result = response.chunk() => result.map_err(|_| "Local model stream interrupted")?,
            _ = tokio::time::sleep(Duration::from_millis(100)) => {
                if cancelled.load(Ordering::Relaxed) { return Err("Cancelled".into()); }
                continue;
            }
        };
        let Some(chunk) = chunk else {
            return Err("Local model stream ended without confirmation".into());
        };
        pending.extend_from_slice(&chunk);
        if pending.len() > 1_048_576 {
            return Err("Local model stream line exceeds its limit".into());
        }
        while let Some(end) = pending.iter().position(|byte| *byte == b'\n') {
            let mut line: Vec<u8> = pending.drain(..=end).collect();
            if line.last() == Some(&b'\n') {
                line.pop();
            }
            if line.last() == Some(&b'\r') {
                line.pop();
            }
            if line.is_empty() {
                continue;
            }
            let (delta, done, reason) = parse_line(&line)?;
            if !delta.is_empty() {
                answer.push_str(&delta);
                if answer.len() > MAX_RESPONSE_BYTES {
                    return Err("Local model answer exceeds its limit".into());
                }
                app.emit(
                    "axx-chat-stream",
                    json!({"request_id": request_id, "delta": delta}),
                )
                .map_err(|_| "Cannot deliver live chat response")?;
            }
            if done {
                if answer.trim().is_empty() {
                    return Err("Local model returned no answer".into());
                }
                return Ok(json!({"text": answer, "reason": reason,
                                 "route": {"provider": "ollama-local", "model": model,
                                           "streamed_local": true}}));
            }
        }
    }
}

#[tauri::command]
pub async fn ollama_realtime_warmup(app: AppHandle, model: String) -> Result<bool, String> {
    validate_model(&model)?;
    verify_local_model(&app, &model).await?;
    let response = local_client()?
        .post("http://127.0.0.1:11434/api/generate")
        .json(&json!({"model": model, "prompt": "", "stream": false, "keep_alive": "30m"}))
        .send()
        .await
        .map_err(|_| "Cannot preload local Ollama model")?;
    if !response.status().is_success() {
        return Err(format!(
            "Local Ollama preload returned HTTP {}",
            response.status().as_u16()
        ));
    }
    Ok(true)
}

#[tauri::command]
pub async fn ollama_realtime_chat(
    app: AppHandle,
    request_id: String,
    model: String,
    messages: Vec<Value>,
) -> Result<Value, String> {
    uuid::Uuid::parse_str(&request_id).map_err(|_| "Invalid request id")?;
    validate_messages(&model, &messages)?;
    let cancelled = Arc::new(AtomicBool::new(false));
    {
        let state = app.state::<HostState>();
        let mut streams = state.realtime_cancellations.lock().unwrap();
        if streams.len() >= 2 {
            return Err("Live chat is busy".into());
        }
        if streams.contains_key(&request_id) {
            return Err("Duplicate request id".into());
        }
        streams.insert(request_id.clone(), cancelled.clone());
        state
            .active_requests
            .lock()
            .unwrap()
            .insert(request_id.clone());
    }
    let result = stream_local(&app, &request_id, &model, &messages, &cancelled).await;
    let state = app.state::<HostState>();
    state
        .realtime_cancellations
        .lock()
        .unwrap()
        .remove(&request_id);
    state.active_requests.lock().unwrap().remove(&request_id);
    result
}

#[tauri::command]
pub fn ollama_realtime_cancel(app: AppHandle, request_id: String) -> Result<bool, String> {
    uuid::Uuid::parse_str(&request_id).map_err(|_| "Invalid request id")?;
    let state = app.state::<HostState>();
    let cancelled = state
        .realtime_cancellations
        .lock()
        .unwrap()
        .get(&request_id)
        .cloned();
    if let Some(cancelled) = cancelled {
        cancelled.store(true, Ordering::Relaxed);
        return Ok(true);
    }
    Ok(false)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_untrusted_history() {
        assert!(
            validate_messages("qwen2.5:3b", &[json!({"role":"user","content":"hola"})]).is_ok()
        );
        assert!(
            validate_messages("qwen2.5:3b", &[json!({"role":"tool","content":"run"})]).is_err()
        );
        assert!(parse_line(br#"{"message":{"content":"Hola"},"done":false}"#).is_ok());
        assert!(parse_line(br#"{"error":"bad"}"#).is_err());
    }
}
