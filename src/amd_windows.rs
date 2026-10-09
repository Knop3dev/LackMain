use crate::telemetry::Reading;


use libloading::Library;
use std::{collections::HashSet,ffi::c_void};
type Context=*mut c_void;
type Allocate=unsafe extern "system" fn(i32)->*mut c_void;
struct Allocator{_lib:Library,malloc:unsafe extern "C" fn(usize)->*mut c_void}
static ALLOCATOR:std::sync::OnceLock<Allocator>=std::sync::OnceLock::new();
#[cfg(target_os="windows")]
unsafe extern "system" fn allocate(n:i32)->*mut c_void{if n<=0{std::ptr::null_mut()}else{ALLOCATOR.get().map(|a|(a.malloc)(n as usize)).unwrap_or(std::ptr::null_mut())}}
#[repr(C)]
struct Adapter{size:i32,index:i32,udid:[u8;256],bus:i32,device:i32,function:i32,vendor:i32,
    name:[u8;256],display:[u8;256],present:i32,exist:i32,driver:[u8;256],driver_ext:[u8;256],pnp:[u8;256],os_index:i32}
#[repr(C)]
#[derive(Clone,Copy)]
struct Sensor{supported:i32,value:i32}
#[repr(C)]
struct Metrics{size:i32,sensors:[Sensor;256]}
type Query=unsafe extern "C" fn(Context,i32,*mut Metrics)->i32;
type Destroy=unsafe extern "C" fn(Context)->i32;
pub struct Telemetry{_lib:Library,context:Context,index:i32,query:Query,destroy:Destroy}
impl Telemetry{
    pub fn adapter_index(&self)->i32 {self.index}
    pub fn new(pci:&str)->Option<Self>{
        #[cfg(target_os="windows")] {unsafe{Self::create(pci).ok()}}
        #[cfg(not(target_os="windows"))] {let _=pci;None}
    }
    #[cfg(target_os="windows")]
    unsafe fn create(pci:&str)->Result<Self,String>{
        if ALLOCATOR.get().is_none(){let crt=Library::new("msvcrt.dll").map_err(|e|e.to_string())?;let malloc=*crt.get(b"malloc\0").map_err(|e|e.to_string())?;let _=ALLOCATOR.set(Allocator{_lib:crt,malloc});}
        let lib=Library::new("atiadlxx.dll").map_err(|e|e.to_string())?;
        let create=*lib.get::<unsafe extern "C" fn(Allocate,i32,*mut Context)->i32>(b"ADL2_Main_Control_Create\0").map_err(|e|e.to_string())?;
        let number=*lib.get::<unsafe extern "C" fn(Context,*mut i32)->i32>(b"ADL2_Adapter_NumberOfAdapters_Get\0").map_err(|e|e.to_string())?;
        let info=*lib.get::<unsafe extern "C" fn(Context,*mut Adapter,i32)->i32>(b"ADL2_Adapter_AdapterInfo_Get\0").map_err(|e|e.to_string())?;
        let query=*lib.get::<Query>(b"ADL2_New_QueryPMLogData_Get\0").map_err(|e|e.to_string())?;
        let destroy=*lib.get::<Destroy>(b"ADL2_Main_Control_Destroy\0").map_err(|e|e.to_string())?;
        let mut context=std::ptr::null_mut();if create(allocate,1,&mut context)!=0{return Err("ADL init failed".into());}
        let result=(||{
            let mut n=0;if number(context,&mut n)!=0||n<=0||n>128{return Err("ADL adapters unavailable".into());}
            let mut adapters:Vec<Adapter>=(0..n).map(|_|std::mem::zeroed()).collect();
            for a in &mut adapters{a.size=std::mem::size_of::<Adapter>() as i32;}
            if info(context,adapters.as_mut_ptr(),(adapters.len()*std::mem::size_of::<Adapter>()) as i32)!=0{return Err("ADL adapter info failed".into());}
            let mut seen=HashSet::new();let unique:Vec<_>=adapters.iter().filter(|a|a.present!=0&&a.bus>=0&&seen.insert((a.bus,a.device,a.function))).collect();
            let (_,loc)=pci.split_once(":").ok_or("Invalid PCI address")?;
            let (bus,loc)=loc.split_once(":").ok_or("Invalid PCI address")?;let (dev,fun)=loc.split_once(".").ok_or("Invalid PCI address")?;
            let bus=i32::from_str_radix(bus,16).map_err(|e|e.to_string())?;let dev=i32::from_str_radix(dev,16).map_err(|e|e.to_string())?;let fun=fun.parse::<i32>().map_err(|e|e.to_string())?;
            let a=unique.iter().find(|a|a.bus==bus && a.device==dev && a.function==fun).ok_or("Matching ADL PCI adapter not found")?;
            Ok(a.index)
        })();
        match result{Ok(index)=>Ok(Self{_lib:lib,context,index,query,destroy}),Err(e)=>{destroy(context);Err(e)}}
    }
    pub fn read(&self)->Option<Reading>{unsafe{
        let mut m=Metrics{size:std::mem::size_of::<Metrics>() as i32,sensors:[Sensor{supported:0,value:0};256]};
        if (self.query)(self.context,self.index,&mut m)!=0{return None;}
        let value=|i:usize|if m.sensors[i].supported!=0{Some(m.sensors[i].value)}else{None};
        Some(Reading{power:value(23).filter(|v|*v>0).map(|v|v as f64),temperature:value(8),utilization:value(19),hotspot:value(27),fan_percent:value(15),core_clock:value(1),memory_clock:value(2)})
    }}
}
impl Drop for Telemetry{fn drop(&mut self){unsafe{(self.destroy)(self.context);}}}
