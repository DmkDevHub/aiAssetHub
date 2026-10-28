use serde::Serialize;
use std::path::{Component, Path, PathBuf, Prefix};
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};

#[derive(Default, Clone)]
pub struct FolderPicker {
    busy: Arc<AtomicBool>,
    selected: Arc<Mutex<Option<String>>>,
}

struct PickerLease(Arc<AtomicBool>);
impl Drop for PickerLease {
    fn drop(&mut self) {
        self.0.store(false, Ordering::Release);
    }
}

#[derive(Serialize)]
pub struct PickedFolder {
    pub path: String,
}

impl FolderPicker {
    /// The desktop adapter supplies the picker. Tests supply a closure without opening UI.
    pub fn choose(
        &self,
        pick: impl FnOnce() -> Result<Option<PathBuf>, &'static str>,
    ) -> Result<Option<PickedFolder>, &'static str> {
        self.busy
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| "FOLDER_PICKER_BUSY")?;
        let _lease = PickerLease(self.busy.clone());
        let result = pick()?.map(|path| validate_folder(&path)).transpose()?;
        if let Some(folder) = &result {
            *self.selected.lock().map_err(|_| "FOLDER_PICK_FAILED")? = Some(folder.path.clone());
        }
        Ok(result)
    }

    pub fn registration_path(&self, requested: &str) -> Result<String, &'static str> {
        if self
            .selected
            .lock()
            .map_err(|_| "FOLDER_PICK_FAILED")?
            .as_deref()
            != Some(requested)
        {
            return Err("FOLDER_SELECTION_CHANGED");
        }
        Ok(validate_folder(Path::new(requested))?.path)
    }
}

fn disk_letter(path: &Path) -> Result<u8, &'static str> {
    if !path.is_absolute()
        || path
            .components()
            .any(|part| matches!(part, Component::ParentDir))
    {
        return Err("FOLDER_LOCAL_ONLY");
    }
    let letter = match path.components().next() {
        Some(Component::Prefix(prefix)) => match prefix.kind() {
            Prefix::Disk(letter) | Prefix::VerbatimDisk(letter) => letter,
            _ => return Err("FOLDER_LOCAL_ONLY"),
        },
        _ => return Err("FOLDER_LOCAL_ONLY"),
    };
    if !path
        .components()
        .any(|part| matches!(part, Component::Normal(_)))
    {
        return Err("FOLDER_ROOT_NOT_ALLOWED");
    }
    Ok(letter)
}

fn allowed_drive(kind: u32) -> bool {
    matches!(kind, 2 | 3 | 5 | 6)
}

#[cfg(windows)]
fn require_local_drive(letter: u8) -> Result<(), &'static str> {
    #[link(name = "kernel32")]
    unsafe extern "system" {
        #[link_name = "GetDriveTypeW"]
        fn get_drive_type_w(root: *const u16) -> u32;
    }
    let root = [u16::from(letter), b':' as u16, b'\\' as u16, 0];
    // SAFETY: root is a live, NUL-terminated UTF-16 drive root with a trailing slash.
    if allowed_drive(unsafe { get_drive_type_w(root.as_ptr()) }) {
        Ok(())
    } else {
        Err("FOLDER_LOCAL_ONLY")
    }
}

#[cfg(not(windows))]
fn require_local_drive(_letter: u8) -> Result<(), &'static str> {
    Err("FOLDER_LOCAL_ONLY")
}

fn validate_folder(path: &Path) -> Result<PickedFolder, &'static str> {
    require_local_drive(disk_letter(path)?)?;
    let canonical = path.canonicalize().map_err(|_| "FOLDER_UNAVAILABLE")?;
    require_local_drive(disk_letter(&canonical)?)?;
    if !canonical.is_dir() {
        return Err("FOLDER_UNAVAILABLE");
    }
    let text = canonical.to_str().ok_or("FOLDER_UNAVAILABLE")?;
    Ok(PickedFolder {
        path: text.strip_prefix(r"\\?\").unwrap_or(text).to_owned(),
    })
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;

    #[test]
    fn cancellation_and_adapter_failure_release_the_picker() {
        let picker = FolderPicker::default();
        assert!(picker.choose(|| Ok(None)).unwrap().is_none());
        assert_eq!(
            picker.choose(|| Err("FOLDER_PICK_FAILED")).err(),
            Some("FOLDER_PICK_FAILED")
        );
        assert!(picker.choose(|| Ok(None)).unwrap().is_none());
    }

    #[test]
    fn duplicate_picker_is_blocked_and_panic_unwinds_the_lease() {
        let picker = FolderPicker::default();
        picker
            .choose(|| {
                assert_eq!(
                    picker
                        .choose(|| panic!("must not open a second picker"))
                        .err(),
                    Some("FOLDER_PICKER_BUSY")
                );
                Ok(None)
            })
            .unwrap();
        let _ = std::panic::catch_unwind(|| picker.choose(|| panic!("fixture adapter failure")));
        assert!(picker.choose(|| Ok(None)).unwrap().is_none());
    }

    #[test]
    fn unc_device_relative_traversal_and_drive_roots_are_rejected_before_io() {
        for path in [
            r"\\server\share\folder",
            r"\\?\UNC\server\share\folder",
            r"\\.\device",
            r"relative\folder",
            r"C:folder",
            r"C:\folder\..",
        ] {
            assert_eq!(disk_letter(Path::new(path)), Err("FOLDER_LOCAL_ONLY"));
        }
        assert_eq!(
            disk_letter(Path::new(r"C:\")),
            Err("FOLDER_ROOT_NOT_ALLOWED")
        );
        assert_eq!(
            disk_letter(Path::new(r"\\?\C:\")),
            Err("FOLDER_ROOT_NOT_ALLOWED")
        );
        assert_eq!(disk_letter(Path::new(r"C:\한글 폴더")), Ok(b'C'));
    }

    #[test]
    fn mapped_network_and_unknown_drives_are_not_local() {
        for kind in [0, 1, 4, 99] {
            assert!(!allowed_drive(kind));
        }
        for kind in [2, 3, 5, 6] {
            assert!(allowed_drive(kind));
        }
    }

    #[test]
    fn selected_real_folder_is_read_only_and_files_missing_paths_are_rejected() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../.artifacts/folder-tests")
            .join(uuid::Uuid::new_v4().to_string());
        let directory = root.join("한글 선택 폴더");
        std::fs::create_dir_all(&directory).unwrap();
        let root = root.canonicalize().unwrap();
        let directory = root.join("한글 선택 폴더");
        let file = directory.join("fixture-original.txt");
        std::fs::write(&file, "fixture unchanged").unwrap();
        let picker = FolderPicker::default();
        assert_eq!(
            picker.registration_path("D:\\unselected").err(),
            Some("FOLDER_SELECTION_CHANGED")
        );
        let result = picker
            .choose(|| Ok(Some(directory.clone())))
            .unwrap()
            .unwrap();
        assert_eq!(picker.registration_path(&result.path).unwrap(), result.path);
        assert_eq!(
            picker.registration_path("D:\\unselected").err(),
            Some("FOLDER_SELECTION_CHANGED")
        );
        assert_eq!(
            Path::new(&result.path).canonicalize().unwrap(),
            directory.canonicalize().unwrap()
        );
        assert_eq!(std::fs::read_to_string(&file).unwrap(), "fixture unchanged");
        assert_eq!(std::fs::read_dir(&directory).unwrap().count(), 1);
        assert_eq!(
            picker.choose(|| Ok(Some(file))).err(),
            Some("FOLDER_UNAVAILABLE")
        );
        assert_eq!(
            picker.choose(|| Ok(Some(root.join("missing")))).err(),
            Some("FOLDER_UNAVAILABLE")
        );
    }
}
