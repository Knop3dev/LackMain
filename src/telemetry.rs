use crate::opencl::DeviceIdentity;
use serde::Serialize;
#[path="nvidia.rs"] mod nvidia;
use std::process::Command;
#[cfg(target_os="linux")] use std::path::PathBuf;
#[cfg(windows)]
#[path="amd_windows.rs"]
mod amd_windows;
#[derive(Clone, Copy, Default, Debug, Serialize)]
pub struct Reading {
    pub power:Option<f64>,pub temperature:Option<i32>,pub utilization:Option<i32>,
    pub hotspot:Option<i32>,pub fan_percent:Option<i32>,pub core_clock:Option<i32>,pub memory_clock:Option<i32>,
}
enum Backend {
    #[cfg(windows)] Amd(amd_windows::Telemetry),
    #[cfg(target_os="linux")] Sysfs{device:PathBuf,hwmon:PathBuf},
    Nvidia(String),
    Nvml(nvidia::Telemetry),
}
pub struct Telemetry{backend:Backend,pub name:String,pub power_kind:&'static str}
fn number<T:std::str::FromStr>(s:&str)->Option<T>{s.trim().parse().ok()}
impl Telemetry {
    pub fn new(id:&DeviceIdentity)->Option<Self>{
        let pci=id.pci.as_deref()?;
        if id.vendor.contains("NVIDIA") {
            if let Some(t)=nvidia::Telemetry::new(pci){return Some(Self{backend:Backend::Nvml(t),name:id.name.clone(),power_kind:"nvidia-board"});}
            return Some(Self{backend:Backend::Nvidia(pci.into()),name:id.name.clone(),power_kind:"nvidia-board"});
        }
        #[cfg(windows)] {
            let backend=amd_windows::Telemetry::new(pci)?;
            return Some(Self{backend:Backend::Amd(backend),name:id.name.clone(),power_kind:"amd-asic"});
        }
        #[cfg(target_os="linux")] {
            let device=PathBuf::from("/sys/bus/pci/devices").join(pci);
            let hwmon=std::fs::read_dir(device.join("hwmon")).ok()?.filter_map(Result::ok)
                .map(|e|e.path()).find(|p|std::fs::read_to_string(p.join("name")).ok().map(|s|s.trim()=="amdgpu").unwrap_or(false))?;
            return Some(Self{backend:Backend::Sysfs{device,hwmon},name:id.name.clone(),power_kind:"amd-soc"});
        }
        #[allow(unreachable_code)] None
    }
    pub fn read(&self)->Option<Reading>{match &self.backend {
        Backend::Nvml(t)=>Some(t.read()),
        #[cfg(windows)] Backend::Amd(t)=>t.read(),
        #[cfg(target_os="linux")] Backend::Sysfs{device,hwmon}=>{
            let n=|file:&str|std::fs::read_to_string(hwmon.join(file)).ok().and_then(|s|number::<f64>(&s));
            let mut hotspot=None;
            for i in 1..=3 {if std::fs::read_to_string(hwmon.join(format!("temp{i}_label"))).ok().map(|s|s.trim().eq_ignore_ascii_case("junction")).unwrap_or(false) {hotspot=n(&format!("temp{i}_input")).map(|v|(v/1000.) as i32);}}
            Some(Reading{power:n("power1_average").or_else(||n("power1_input")).map(|v|v/1e6),
                temperature:n("temp1_input").map(|v|(v/1000.) as i32),hotspot,
                utilization:std::fs::read_to_string(device.join("gpu_busy_percent")).ok().and_then(|s|number(&s)),
                fan_percent:n("pwm1").map(|v|(v*100./255.) as i32),
                core_clock:n("freq1_input").map(|v|(v/1e6) as i32),memory_clock:n("freq2_input").map(|v|(v/1e6) as i32)})
        },
        Backend::Nvidia(pci)=>{
            let out=Command::new("nvidia-smi").args(["-i",pci,"--query-gpu=power.draw,temperature.gpu,utilization.gpu,fan.speed,clocks.current.graphics,clocks.current.memory","--format=csv,noheader,nounits"]).output().ok()?;
            if !out.status.success(){return None;}
            let s=String::from_utf8_lossy(&out.stdout);let v:Vec<_>=s.trim().split(',').collect();if v.len()!=6{return None;}
            Some(Reading{power:number(v[0]),temperature:number(v[1]),utilization:number(v[2]),fan_percent:number(v[3]),core_clock:number(v[4]),memory_clock:number(v[5]),hotspot:None})
        }
    }}
    #[cfg(windows)] pub fn adl_index(&self)->Option<i32>{if let Backend::Amd(t)=&self.backend{Some(t.adapter_index())}else{None}}
    #[cfg(target_os="linux")] pub fn sysfs(&self)->Option<(&std::path::Path,&std::path::Path)>{if let Backend::Sysfs{device,hwmon}=&self.backend{Some((device,hwmon))}else{None}}
}
