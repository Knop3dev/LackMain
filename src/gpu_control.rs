use crate::{opencl::DeviceIdentity, telemetry::{Reading,Telemetry}, Options};
use serde_json::{json,Value};
use std::{fs,path::PathBuf,process::{Child,Command},time::{Duration,Instant}};
#[cfg(target_os="linux")] use std::path::Path;
#[cfg(windows)] use std::{io::{BufRead,BufReader},process::Stdio};

#[derive(Default)]
struct Hardware { files:Vec<(PathBuf,String)>, commands:Vec<(String,Vec<String>)>, helper:Option<Child> }
fn smi(pci:&str,args:&[&str])->Result<String,String>{
    let out=Command::new("nvidia-smi").args(["-i",pci]).args(args).output().map_err(|e|format!("nvidia-smi: {e}"))?;
    if !out.status.success(){return Err(format!("nvidia-smi: {}",String::from_utf8_lossy(&out.stderr).trim()));}
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}
fn number(s:&str)->Result<f64,String>{s.trim().parse().map_err(|_|format!("GPU driver did not report a numeric value: {s}"))}
#[cfg(target_os="linux")] fn read(p:&Path)->Result<String,String>{fs::read_to_string(p).map_err(|e|format!("{}: {e}",p.display()))}
impl Hardware {
    #[cfg(target_os="linux")] fn set_file(&mut self,p:&Path,value:String)->Result<(),String>{
        let old=read(p)?;self.files.push((p.to_owned(),old));
        fs::write(p,&value).map_err(|e|format!("{}: {e}; GPU tuning requires driver permissions",p.display()))?;
        if read(p)?.trim()!=value.trim(){return Err(format!("Driver did not confirm {}",p.display()));}Ok(())
    }
    fn apply(id:&DeviceIdentity,t:Option<&Telemetry>,o:&Options)->Result<Self,String>{
        let mut h=Self::default();
        let requested=o.power_limit.is_some()||o.power_percent.is_some()||o.core_clock.is_some()||o.memory_clock.is_some()||o.fan.is_some();
        if !requested{return Ok(h);}
        let pci=id.pci.as_deref().ok_or("GPU tuning requires an unambiguous PCI identity")?;
        if id.vendor.contains("NVIDIA") {
            if o.power_percent.is_some()||o.fan.is_some(){return Err("NVIDIA: use --power-limit in watts; fan profiles are managed by the driver/Hive OS".into());}
            if let Some(w)=o.power_limit {
                let s=smi(pci,&["--query-gpu=power.limit,power.min_limit,power.max_limit","--format=csv,noheader,nounits"])?;
                let v:Vec<f64>=s.split(',').map(number).collect::<Result<_,_>>()?;
                if v.len()!=3||w<v[1]||w>v[2]{return Err(format!("Power limit outside NVIDIA driver range: {s}"));}
                h.commands.push((pci.into(),vec!["--power-limit".into(),v[0].to_string()]));
                smi(pci,&["--power-limit",&w.to_string()])?;
                let actual=number(&smi(pci,&["--query-gpu=power.limit","--format=csv,noheader,nounits"])?)?;
                if (actual-w).abs()>0.5{return Err("NVIDIA power limit readback mismatch".into());}
            }
            if o.core_clock.is_some()||o.memory_clock.is_some(){
                let old=smi(pci,&["--query-gpu=clocks.applications.memory,clocks.applications.graphics","--format=csv,noheader,nounits"])?;
                let v:Vec<f64>=old.split(',').map(number).collect::<Result<_,_>>()?;
                if v.len()!=2{return Err("Application clocks are unsupported on this NVIDIA driver".into());}
                let new=format!("{},{}",o.memory_clock.map(f64::from).unwrap_or(v[0]),o.core_clock.map(f64::from).unwrap_or(v[1]));
                h.commands.push((pci.into(),vec!["--applications-clocks".into(),format!("{},{}",v[0],v[1])]));
                smi(pci,&["--applications-clocks",&new])?;
                let actual=smi(pci,&["--query-gpu=clocks.applications.memory,clocks.applications.graphics","--format=csv,noheader,nounits"])?;
                if actual.replace(' ',"")!=new{return Err("NVIDIA application clock readback mismatch".into());}
            }
            return Ok(h);
        }
        #[cfg(target_os="linux")] {
            let (device,hwmon)=t.and_then(Telemetry::sysfs).ok_or("AMD sysfs tuning is unavailable for the selected PCI GPU")?;
            if o.power_percent.is_some(){return Err("Linux AMD: use --power-limit in watts".into());}
            if let Some(w)=o.power_limit {
                let minimum=number(&read(&hwmon.join("power1_cap_min"))?)?/1e6;
                let maximum=number(&read(&hwmon.join("power1_cap_max"))?)?/1e6;
                if w<minimum||w>maximum{return Err(format!("AMD power range: {minimum}..{maximum} W"));}
                h.set_file(&hwmon.join("power1_cap"),format!("{}",(w*1e6).round() as u64))?;
            }
            if o.core_clock.is_some()||o.memory_clock.is_some(){
                let od=device.join("pp_od_clk_voltage");let old=read(&od)?;
                let mut section="";let mut original=Vec::new();
                for line in old.lines(){
                    if line.starts_with("OD_"){section=line;continue;}
                    if (section=="OD_SCLK:"&&o.core_clock.is_some())||(section=="OD_MCLK:"&&o.memory_clock.is_some()) {
                        if let Some(rest)=line.trim().strip_prefix("1:") {
                            let current=rest.split_whitespace().next().ok_or("Invalid AMD OD clock")?.trim_end_matches("Mhz").parse::<u32>().map_err(|e|e.to_string())?;
                            let (kind,want)=if section=="OD_SCLK:" {('s',o.core_clock.unwrap())}else{('m',o.memory_clock.unwrap())};
                            if want>current{return Err("AMD clock settings permit reductions from the captured profile only".into());}
                            original.push((kind,current,want));
                        }
                    }
                }
                if original.len()!=o.core_clock.is_some() as usize+o.memory_clock.is_some() as usize{return Err("AMD driver does not expose the required OD_SCLK/OD_MCLK states".into());}
                h.set_file(&device.join("power_dpm_force_performance_level"),"manual".into())?;
                
                for (kind,current,want) in &original {
                    h.files.push((od.clone(),format!("{kind} 1 {current}\nc")));
                    fs::write(&od,format!("{kind} 1 {want}")).map_err(|e|e.to_string())?;
                }
                fs::write(&od,"c").map_err(|e|e.to_string())?;
                let actual=read(&od)?;
                for (kind,_,want) in &original {
                    let marker=if *kind=='s'{"OD_SCLK:"}else{"OD_MCLK:"};
                    let mut section="";let mut confirmed=false;
                    for line in actual.lines(){
                        if line.starts_with("OD_"){section=line;continue;}
                        if section==marker {if let Some(rest)=line.trim().strip_prefix("1:"){
                            confirmed=rest.split_whitespace().next().and_then(|v|v.trim_end_matches("Mhz").parse::<u32>().ok())==Some(*want);
                        }}
                    }
                    if !confirmed{return Err(format!("AMD driver did not confirm {marker} {want} MHz"));}
                }
            }
            if let Some(fan)=o.fan {h.set_file(&hwmon.join("pwm1_enable"),"1".into())?;h.set_file(&hwmon.join("pwm1"),((u32::from(fan)*255+50)/100).to_string())?;}
            return Ok(h);
        }
        #[cfg(windows)] {
            if o.power_limit.is_some(){return Err("Windows AMD uses --max-power (measured ASIC budget) or --power-percent (driver power limit)".into());}
            if o.memory_clock.is_some()||o.fan.is_some(){return Err("Windows AMD: memory/fan profiles are managed in Radeon settings; this build controls core clock and power percent".into());}
            let index=t.and_then(Telemetry::adl_index).ok_or("Matching AMD ADL PCI adapter is unavailable")?;
            let helper=std::env::current_exe().map_err(|e|e.to_string())?.with_file_name("lackminer-gpu-control.exe");
            let mut cmd=Command::new(helper);cmd.arg(format!("--adl-index={index}"));
            if let Some(v)=o.power_percent{cmd.arg(format!("--power-limit={v}"));}
            if let Some(v)=o.core_clock{cmd.arg(format!("--max-frequency={v}"));}
            let mut child=cmd.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::inherit()).spawn().map_err(|e|format!("AMD tuning helper: {e}"))?;
            let stdout=child.stdout.take().ok_or("AMD helper stdout missing")?;
            h.helper=Some(child);
            let mut lines=BufReader::new(stdout).lines();
            let first=lines.next().ok_or("AMD helper reported no capabilities")?.map_err(|e|e.to_string())?;
            let confirmed=lines.next().ok_or("AMD helper did not confirm tuning")?.map_err(|e|e.to_string())?;
            let _:Value=serde_json::from_str(&first).map_err(|e|e.to_string())?;
            let result:Value=serde_json::from_str(&confirmed).map_err(|e|e.to_string())?;
            if o.core_clock.is_some_and(|v|result["applied_max_frequency_mhz"]!=v)||o.power_percent.is_some_and(|v|result["applied_power_limit_percent"]!=v){return Err("AMD driver did not confirm requested settings".into());}
            return Ok(h);
        }
        #[allow(unreachable_code)] Err("GPU tuning is unsupported on this OS".into())
    }
}
impl Drop for Hardware {
    fn drop(&mut self){
        if let Some(mut c)=self.helper.take(){drop(c.stdin.take());let _=c.wait();}
        for (pci,args) in self.commands.iter().rev(){let refs:Vec<_>=args.iter().map(String::as_str).collect();if let Err(e)=smi(pci,&refs){eprintln!("GPU restore error: {e}");}}
        for (p,v) in self.files.iter().rev(){for line in v.lines(){if let Err(e)=fs::write(p,line){eprintln!("GPU restore error {}: {e}",p.display());}}}
    }
}
#[derive(Default)]
pub struct Policy { pub power:Option<f64>,pub temperature:Option<i32>,pub hotspot:Option<i32>,thermal_paused:bool,power_paused:bool }
impl Policy {
    pub fn phase(&mut self,r:Option<Reading>)->&'static str {
        let protected=self.power.is_some()||self.temperature.is_some()||self.hotspot.is_some();
        let Some(r)=r else {return if protected {"sensor_unavailable"}else{"mining"};};
        if (self.power.is_some()&&r.power.is_none())||(self.temperature.is_some()&&r.temperature.is_none())||(self.hotspot.is_some()&&r.hotspot.is_none()){return "sensor_unavailable";}
        let over=self.temperature.zip(r.temperature).is_some_and(|(lim,v)|v>lim)||self.hotspot.zip(r.hotspot).is_some_and(|(lim,v)|v>lim);
        let cooled=self.temperature.zip(r.temperature).is_none_or(|(lim,v)|v<=lim-5)&&self.hotspot.zip(r.hotspot).is_none_or(|(lim,v)|v<=lim-5);
        if over{self.thermal_paused=true;}else if cooled{self.thermal_paused=false;}
        if self.thermal_paused{return "cooling";}
        if let Some((lim,power))=self.power.zip(r.power){if power>lim{self.power_paused=true;}else if power<=lim*0.95{self.power_paused=false;}}
        if self.power_paused{"power_wait"}else{"mining"}
    }
}
pub struct Monitor { _hardware:Hardware,telemetry:Option<Telemetry>,pub reading:Option<Reading>,policy:Policy,sampled:Instant,pub phase:&'static str,intensity:u8 }
impl Monitor {
    pub fn new(id:&DeviceIdentity,o:&Options)->Result<Self,String>{
        let telemetry=Telemetry::new(id);let reading=telemetry.as_ref().and_then(Telemetry::read);
        let mut policy=Policy{power:o.max_power,temperature:o.max_temp.or_else(||reading.and_then(|r|r.temperature.map(|_|80))),hotspot:o.max_hotspot.or_else(||reading.and_then(|r|r.hotspot.map(|_|80))),..Default::default()};
        if policy.phase(reading)=="sensor_unavailable"{return Err("Requested power/temperature protection requires real sensors for the selected PCI GPU".into());}
        let hardware=Hardware::apply(id,telemetry.as_ref(),o)?;
        println!("GPU controls: PCI {} | power sensor {} | max-power {:?} W | temperature {:?} C | hotspot {:?} C | intensity {}%",id.pci.as_deref().unwrap_or("unknown"),telemetry.as_ref().map(|t|t.power_kind).unwrap_or("unavailable"),o.max_power,policy.temperature,policy.hotspot,o.intensity);
        Ok(Self{_hardware:hardware,telemetry,reading,policy,sampled:Instant::now()-Duration::from_secs(1),phase:"mining",intensity:o.intensity})
    }
    pub fn ready(&mut self)->bool{
        if self.sampled.elapsed()>=Duration::from_millis(250){self.reading=self.telemetry.as_ref().and_then(Telemetry::read);self.phase=self.policy.phase(self.reading);self.sampled=Instant::now();}
        self.phase=="mining"
    }
    pub fn after_dispatch(&self,elapsed:Duration){if self.intensity<100{std::thread::sleep(elapsed.mul_f64(100.0/f64::from(self.intensity)-1.0));}}
    pub fn stats(&self)->Value{json!({"phase":self.phase,"gpu":self.reading,"power_kind":self.telemetry.as_ref().map(|t|t.power_kind),"intensity":self.intensity})}
}

#[cfg(test)] mod tests {
    use super::*;
    #[test] fn thermal_hysteresis_and_missing_sensor_fail_closed(){let mut p=Policy{hotspot:Some(80),..Default::default()};let r=|v|Some(Reading{hotspot:Some(v),..Default::default()});assert_eq!(p.phase(r(81)),"cooling");assert_eq!(p.phase(r(79)),"cooling");assert_eq!(p.phase(None),"sensor_unavailable");assert_eq!(p.phase(r(75)),"mining");}
    #[test] fn power_wait_does_not_resume_at_the_limit(){let mut p=Policy{power:Some(120.),..Default::default()};let r=|v|Some(Reading{power:Some(v),..Default::default()});assert_eq!(p.phase(r(121.)),"power_wait");assert_eq!(p.phase(r(119.)),"power_wait");assert_eq!(p.phase(r(113.)),"mining");}
}
