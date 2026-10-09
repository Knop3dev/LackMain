
#![allow(non_snake_case)] 
use libloading::Library;
use std::ffi::{c_void, CString};
const NONCES_PER_ITEM:usize=2;
#[path="segment.rs"]
mod segment;
type Handle = *mut c_void;
type I = i32;
type U = u32;
type L = u64;
type Callback = Option<unsafe extern "system" fn(*const i8, *const c_void, usize, *mut c_void)>;
macro_rules! api {
    ($($name:ident: $ty:ty),* $(,)?) => {
        struct Api { _lib: Library, $($name: $ty,)* }
        impl Api {
            unsafe fn load() -> Result<Self,String> {
                let mut errors=Vec::new();
                #[cfg(target_os="windows")]
                let names:&[&str]=&["OpenCL.dll"];
                #[cfg(target_os="linux")]
                let names:&[&str]=&["libOpenCL.so.1","libOpenCL.so"];
                #[cfg(target_os="macos")]
                let names:&[&str]=&["/System/Library/Frameworks/OpenCL.framework/OpenCL"];
                #[cfg(not(any(target_os="windows",target_os="linux",target_os="macos")))]
                let names:&[&str]=&[];
                let mut loaded=None;
                for name in names {match Library::new(name){Ok(lib)=>{loaded=Some(lib);break;},Err(e)=>errors.push(format!("{name}: {e}"))}}
                let lib=loaded.ok_or_else(||format!("OpenCL loader unavailable ({})",errors.join("; ")))?;
                $(let $name = *lib.get::<$ty>(concat!(stringify!($name),"\0").as_bytes()).map_err(|e|e.to_string())?;)*
                Ok(Self { _lib:lib, $($name,)* })
            }
        }
    }
}
api! {
clGetPlatformIDs: unsafe extern "system" fn(U,*mut Handle,*mut U)->I,
clGetDeviceIDs: unsafe extern "system" fn(Handle,L,U,*mut Handle,*mut U)->I,
clGetDeviceInfo: unsafe extern "system" fn(Handle,U,usize,*mut c_void,*mut usize)->I,
clCreateContext: unsafe extern "system" fn(*const isize,U,*const Handle,Callback,*mut c_void,*mut I)->Handle,
clCreateCommandQueue: unsafe extern "system" fn(Handle,Handle,L,*mut I)->Handle,
clCreateProgramWithSource: unsafe extern "system" fn(Handle,U,*const *const i8,*const usize,*mut I)->Handle,
clBuildProgram: unsafe extern "system" fn(Handle,U,*const Handle,*const i8,Option<unsafe extern "system" fn(Handle,*mut c_void)>,*mut c_void)->I,
clGetProgramBuildInfo: unsafe extern "system" fn(Handle,Handle,U,usize,*mut c_void,*mut usize)->I,
clCreateKernel: unsafe extern "system" fn(Handle,*const i8,*mut I)->Handle,
clGetKernelWorkGroupInfo: unsafe extern "system" fn(Handle,Handle,U,usize,*mut c_void,*mut usize)->I,
clCreateBuffer: unsafe extern "system" fn(Handle,L,usize,*mut c_void,*mut I)->Handle,
clSetKernelArg: unsafe extern "system" fn(Handle,U,usize,*const c_void)->I,
clEnqueueWriteBuffer: unsafe extern "system" fn(Handle,Handle,U,usize,usize,*const c_void,U,*const Handle,*mut Handle)->I,
clEnqueueReadBuffer: unsafe extern "system" fn(Handle,Handle,U,usize,usize,*mut c_void,U,*const Handle,*mut Handle)->I,
clEnqueueNDRangeKernel: unsafe extern "system" fn(Handle,Handle,U,*const usize,*const usize,*const usize,U,*const Handle,*mut Handle)->I,
clWaitForEvents: unsafe extern "system" fn(U,*const Handle)->I,
clGetEventProfilingInfo: unsafe extern "system" fn(Handle,U,usize,*mut c_void,*mut usize)->I,
clReleaseEvent: unsafe extern "system" fn(Handle)->I,
clReleaseMemObject: unsafe extern "system" fn(Handle)->I,
clReleaseKernel: unsafe extern "system" fn(Handle)->I,
clReleaseProgram: unsafe extern "system" fn(Handle)->I,
clReleaseCommandQueue: unsafe extern "system" fn(Handle)->I,
clReleaseContext: unsafe extern "system" fn(Handle)->I,
}
fn check(v:I)->Result<(),String>{if v==0 {Ok(())}else{Err(format!("OpenCL error {v}"))}}
unsafe fn device_text(a:&Api,d:Handle,p:U)->String {
    let mut n=0;(a.clGetDeviceInfo)(d,p,0,std::ptr::null_mut(),&mut n);
    let mut b=vec![0u8;n];(a.clGetDeviceInfo)(d,p,n,b.as_mut_ptr().cast(),std::ptr::null_mut());
    String::from_utf8_lossy(&b).trim_end_matches('\0').to_string()
}
unsafe fn devices(a:&Api)->Result<Vec<Handle>,String>{
    let mut n=0;check((a.clGetPlatformIDs)(0,std::ptr::null_mut(),&mut n))?;
    let mut ps=vec![std::ptr::null_mut();n as usize];check((a.clGetPlatformIDs)(n,ps.as_mut_ptr(),std::ptr::null_mut()))?;
    let mut ds=Vec::new();
    for p in ps {n=0;if (a.clGetDeviceIDs)(p,4,0,std::ptr::null_mut(),&mut n)!=0{continue;}
        let mut found=vec![std::ptr::null_mut();n as usize];check((a.clGetDeviceIDs)(p,4,n,found.as_mut_ptr(),std::ptr::null_mut()))?;ds.extend(found);}
    Ok(ds)
}
pub fn list()->Result<(),String>{unsafe{let a=Api::load()?;for (i,d) in devices(&a)?.iter().enumerate(){
    let id=identity(&a,*d);println!("GPU{i}: {} | {} | {} | PCI {}",id.name,id.vendor,device_text(&a,*d,0x102d),id.pci.as_deref().unwrap_or("unavailable"));}Ok(())}}

#[derive(Clone, Debug)]
pub struct DeviceIdentity { pub name:String, pub vendor:String, pub pci:Option<String> }
unsafe fn identity(a:&Api,d:Handle)->DeviceIdentity {
    let name=device_text(a,d,0x102b);let vendor=device_text(a,d,0x102c);
    let mut pci=None;let mut info=[0u32;4];
    if (a.clGetDeviceInfo)(d,0x410f,16,info.as_mut_ptr().cast(),std::ptr::null_mut())==0 {
        pci=Some(format!("{:04x}:{:02x}:{:02x}.{}",info[0],info[1],info[2],info[3]));
    } else if vendor.contains("AMD") || vendor.contains("Advanced Micro") {
        let mut topo=[0u8;24];
        if (a.clGetDeviceInfo)(d,0x4037,24,topo.as_mut_ptr().cast(),std::ptr::null_mut())==0 && u32::from_ne_bytes(topo[..4].try_into().unwrap())==1 {
            pci=Some(format!("0000:{:02x}:{:02x}.{}",topo[21],topo[22],topo[23]));
        }
    }
    if pci.is_none() && vendor.contains("NVIDIA") {
        if let Ok(rows)=std::process::Command::new("nvidia-smi").args(["--query-gpu=name,pci.bus_id","--format=csv,noheader,nounits"]).output() {
            let text=String::from_utf8_lossy(&rows.stdout);let matches:Vec<_>=text.lines().filter_map(|l|l.split_once(", ")).filter(|(n,_)|*n==name).collect();
            let cl_matches=devices(a).unwrap_or_default().into_iter().filter(|other|device_text(a,*other,0x102b)==name).count();
            if matches.len()==1 && cl_matches==1 {let b=matches[0].1.trim().to_lowercase();pci=Some(if b.len()==16 {b[4..].to_string()}else{b});}
        }
    }
    DeviceIdentity{name,vendor,pci}
}
pub struct Gpu {a:Api,context:Handle,queue:Handle,program:Handle,search:Handle,test:Handle,
    job:Handle,count:Handle,nonces:Handle,last_target:std::cell::Cell<Option<u64>>,
    job_words:std::cell::RefCell<[u32;32]>,last_high:std::cell::Cell<Option<u32>>,
    pub identity:DeviceIdentity,pub name:String,pub driver:String,pub kernel_info:serde_json::Value}
impl Gpu {
    pub fn new(index:usize,unroll:bool)->Result<Self,String>{unsafe{
        let a=Api::load()?;let ds=devices(&a)?;let d=*ds.get(index).ok_or("GPU index not found")?;
        let mut e=0;let context=(a.clCreateContext)(std::ptr::null(),1,&d,None,std::ptr::null_mut(),&mut e);check(e)?;
        let queue=(a.clCreateCommandQueue)(context,d,2,&mut e);check(e)?;
        let source=CString::new(include_str!("sha256_segment.cl")).unwrap();let ptr=source.as_ptr();
        let program=(a.clCreateProgramWithSource)(context,1,&ptr,std::ptr::null(),&mut e);check(e)?;
        let device_name=device_text(&a,d,0x102b);
        let wave64=device_name=="gfx1031" || device_name.contains("6700 XT");
        let opts=CString::new(format!("-cl-std=CL1.2 -DUNROLL={}{}",unroll as u8,
            if wave64 {" -Wf,-mwavefrontsize64"} else {""})).unwrap();
        if (a.clBuildProgram)(program,1,&d,opts.as_ptr(),None,std::ptr::null_mut())!=0 {
            let mut n=0;(a.clGetProgramBuildInfo)(program,d,0x1183,0,std::ptr::null_mut(),&mut n);
            let mut log=vec![0u8;n];(a.clGetProgramBuildInfo)(program,d,0x1183,n,log.as_mut_ptr().cast(),std::ptr::null_mut());
            return Err(String::from_utf8_lossy(&log).to_string());
        }
        let search=(a.clCreateKernel)(program,c"search".as_ptr(),&mut e);check(e)?;
        let test=(a.clCreateKernel)(program,c"digest_test".as_ptr(),&mut e);check(e)?;
        let job=(a.clCreateBuffer)(context,4,169*4,std::ptr::null_mut(),&mut e);check(e)?;
        let count=(a.clCreateBuffer)(context,1,4,std::ptr::null_mut(),&mut e);check(e)?;
        let nonces=(a.clCreateBuffer)(context,1,4096*8,std::ptr::null_mut(),&mut e);check(e)?;
        let mut wg=0usize;let mut private=0u64;let mut local=0u64;
        check((a.clGetKernelWorkGroupInfo)(search,d,0x11b0,8,(&mut wg as *mut usize).cast(),std::ptr::null_mut()))?;
        check((a.clGetKernelWorkGroupInfo)(search,d,0x11b4,8,(&mut private as *mut u64).cast(),std::ptr::null_mut()))?;
        check((a.clGetKernelWorkGroupInfo)(search,d,0x11b2,8,(&mut local as *mut u64).cast(),std::ptr::null_mut()))?;
        let name=device_text(&a,d,0x102b);let driver=device_text(&a,d,0x102d);
        let device_identity=identity(&a,d);
        let gpu=Self{a,context,queue,program,search,test,job,count,nonces,last_target:std::cell::Cell::new(None),name,driver,
            job_words:std::cell::RefCell::new([0;32]),last_high:std::cell::Cell::new(None),
            identity:device_identity,kernel_info:serde_json::json!({"max_workgroup":wg,"private_bytes":private,"local_bytes":local,"unroll":unroll,"nonces_per_item":NONCES_PER_ITEM,"requested_wave64":wave64,"variant":"scalar2-nonce-segment-precompute"})};
        gpu.arg(search,0,&job)?;gpu.arg(search,3,&count)?;gpu.arg(search,4,&nonces)?;gpu.arg(search,5,&4096u32)?;
        gpu.arg(test,0,&job)?;
        Ok(gpu)
    }}
    fn arg<T>(&self,k:Handle,i:U,v:&T)->Result<(),String>{unsafe{check((self.a.clSetKernelArg)(k,i,std::mem::size_of::<T>(),(v as *const T).cast()))}}
    fn write<T>(&self,b:Handle,v:&[T])->Result<(),String>{unsafe{check((self.a.clEnqueueWriteBuffer)(self.queue,b,1,0,std::mem::size_of_val(v),v.as_ptr().cast(),0,std::ptr::null(),std::ptr::null_mut()))}}
    fn read<T>(&self,b:Handle,v:&mut[T])->Result<(),String>{unsafe{check((self.a.clEnqueueReadBuffer)(self.queue,b,1,0,std::mem::size_of_val(v),v.as_mut_ptr().cast(),0,std::ptr::null(),std::ptr::null_mut()))}}
    pub fn set_job(&self,header:&[u8;120])->Result<(),String>{
        let mut st=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
        let block=sha2::digest::generic_array::GenericArray::clone_from_slice(&header[..64]);
        sha2::compress256(&mut st,&[block]);
        let mut job=[0u32;32];job[..8].copy_from_slice(&st);
        for i in 0..14{job[8+i]=u32::from_be_bytes(header[64+i*4..68+i*4].try_into().unwrap());}
        job[22]=0x80000000;
        
        
        const K:[u32;10]=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,
            0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01];
        let [mut a,mut b,mut c,mut d,mut e,mut f,mut g,mut h]=st;
        for i in 0..10{
            let s1=e.rotate_right(6)^e.rotate_right(11)^e.rotate_right(25);
            let s0=a.rotate_right(2)^a.rotate_right(13)^a.rotate_right(22);
            let t1=h.wrapping_add(s1).wrapping_add((e&f)^(!e&g))
                .wrapping_add(K[i]).wrapping_add(job[8+i]);
            let t2=s0.wrapping_add((a&b)^(a&c)^(b&c));
            h=g;g=f;f=e;e=d.wrapping_add(t1);d=c;c=b;b=a;a=t1.wrapping_add(t2);
        }
        job[24..32].copy_from_slice(&[a,b,c,d,e,f,g,h]);
        *self.job_words.borrow_mut()=job;self.last_high.set(None);
        self.write(self.job,&job)
    }
    fn prepare_segment(&self,base:u64)->Result<(),String>{
        let high=(base>>32) as u32;
        if self.last_high.get()!=Some(high){
            self.write(self.job,&segment::prepare(&self.job_words.borrow(),high))?;
            self.last_high.set(Some(high));
        }
        Ok(())
    }
    fn launch(&self,k:Handle,n:usize,wg:usize)->Result<f64,String>{unsafe{
        if n==0 || wg==0 || n%(wg*NONCES_PER_ITEM)!=0{return Err("Batch must be positive and divisible by worksize * nonces_per_item".into());}
        let global=n/NONCES_PER_ITEM;
        let mut event=std::ptr::null_mut();check((self.a.clEnqueueNDRangeKernel)(self.queue,k,1,std::ptr::null(),&global,&wg,0,std::ptr::null(),&mut event))?;
        check((self.a.clWaitForEvents)(1,&event))?;let mut start=0u64;let mut end=0u64;
        check((self.a.clGetEventProfilingInfo)(event,0x1282,8,(&mut start as *mut u64).cast(),std::ptr::null_mut()))?;
        check((self.a.clGetEventProfilingInfo)(event,0x1283,8,(&mut end as *mut u64).cast(),std::ptr::null_mut()))?;
        (self.a.clReleaseEvent)(event);Ok((end-start) as f64*1e-9)
    }}
    pub fn search(&self,base:u64,target:u64,n:usize,wg:usize)->Result<(Vec<u64>,f64),String>{
        self.prepare_segment(base)?;
        let zero=0u32;
        
        unsafe{check((self.a.clEnqueueWriteBuffer)(self.queue,self.count,0,0,4,(&zero as *const u32).cast(),0,std::ptr::null(),std::ptr::null_mut()))?;}
        self.arg(self.search,1,&base)?;
        if self.last_target.get()!=Some(target){self.arg(self.search,2,&target)?;self.last_target.set(Some(target));}
        let seconds=self.launch(self.search,n,wg)?;let mut count=[0u32];self.read(self.count,&mut count)?;
        if count[0]>4096{return Err(format!("Result overflow: {} shares. Reduce --batch.",count[0]));}
        let mut nonces=vec![0u64;count[0] as usize];if !nonces.is_empty(){self.read(self.nonces,&mut nonces)?;}
        Ok((nonces,seconds))
    }
    pub fn digests(&self,base:u64,n:usize,wg:usize)->Result<Vec<[u8;32]>,String>{unsafe{
        self.prepare_segment(base)?;
        let mut e=0;let out=(self.a.clCreateBuffer)(self.context,1,n*32,std::ptr::null_mut(),&mut e);check(e)?;
        let result=(||{self.arg(self.test,0,&self.job)?;self.arg(self.test,1,&base)?;self.arg(self.test,2,&out)?;
            self.launch(self.test,n,wg)?;let mut data=vec![0u32;n*8];self.read(out,&mut data)?;
            Ok(data.chunks_exact(8).map(|c|{let mut h=[0u8;32];for i in 0..8{h[i*4..i*4+4].copy_from_slice(&c[i].to_be_bytes());}h}).collect())})();
        (self.a.clReleaseMemObject)(out);result
    }}
}
impl Drop for Gpu {fn drop(&mut self){unsafe{
    for b in [self.job,self.count,self.nonces]{(self.a.clReleaseMemObject)(b);}
    for k in [self.search,self.test]{(self.a.clReleaseKernel)(k);}
    (self.a.clReleaseProgram)(self.program);(self.a.clReleaseCommandQueue)(self.queue);(self.a.clReleaseContext)(self.context);
}}}
