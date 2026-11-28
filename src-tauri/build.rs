use std::path::Path;

fn watch_dir(dir: &Path) {
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                watch_dir(&path);
            } else {
                println!("cargo:rerun-if-changed={}", path.display());
            }
        }
    }
}

fn main() {
    println!("cargo:rerun-if-changed=../1.AXX/Axx.html");
    watch_dir(Path::new("../1.AXX/scripts/notch"));
    tauri_build::build()
}
