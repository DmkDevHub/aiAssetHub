pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("AI Asset Hub 실행 실패");
}
