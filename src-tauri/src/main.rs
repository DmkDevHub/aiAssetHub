#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.first().is_some_and(|arg| arg == "--verify-core") {
        if args.len() != 2 {
            std::process::exit(2);
        }
        match ai_asset_hub_lib::verify_packaged_core(std::path::PathBuf::from(&args[1])) {
            Ok(response) => {
                println!("{response}");
                return;
            }
            Err(code) => {
                eprintln!("{code}");
                std::process::exit(1);
            }
        }
    }
    ai_asset_hub_lib::run()
}
