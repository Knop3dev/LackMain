use std::{env,fs,path::PathBuf,process::Command};

fn main(){
    println!("cargo:rerun-if-changed=Cargo.toml");
    if env::var("CARGO_CFG_TARGET_OS").as_deref()!=Ok("windows")||env::var("CARGO_CFG_TARGET_ENV").as_deref()!=Ok("msvc"){return;}
    let version=env::var("CARGO_PKG_VERSION").unwrap();
    let numbers=format!("{},0",version.replace('.',","));
    let resource=format!(r#"1 VERSIONINFO
FILEVERSION {numbers}
PRODUCTVERSION {numbers}
FILEFLAGSMASK 0x3fL
FILEFLAGS 0x0L
FILEOS 0x40004L
FILETYPE 0x1L
FILESUBTYPE 0x0L
BEGIN
 BLOCK "StringFileInfo"
 BEGIN
  BLOCK "040904b0"
  BEGIN
   VALUE "FileDescription", "lackminer Q-BTC CPU and OpenCL miner\0"
   VALUE "FileVersion", "{version}\0"
   VALUE "InternalName", "lackminer-qbtc\0"
   VALUE "OriginalFilename", "lackminer-qbtc.exe\0"
   VALUE "ProductName", "lackminer qbtc\0"
   VALUE "ProductVersion", "{version}\0"
  END
 END
 BLOCK "VarFileInfo"
 BEGIN
  VALUE "Translation", 0x409, 1200
 END
END
"#);
    let out=PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let source=out.join("version.rc");let target=out.join("version.res");
    fs::write(&source,resource).unwrap();
    let status=Command::new("rc.exe").arg("/nologo").arg("/fo").arg(&target).arg(&source).status().expect("Windows SDK rc.exe is required");
    assert!(status.success(),"Windows version resource compilation failed");
    println!("cargo:rustc-link-arg={}",target.display());
}
