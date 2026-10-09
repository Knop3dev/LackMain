mod opencl;
mod telemetry;
mod gpu_control;
mod solo;
mod pow;
mod nonce;
use std::time::{Duration, Instant};
use std::sync::{Arc, Barrier};
use serde_json::json;
static SIGNAL_STOP:std::sync::atomic::AtomicBool=std::sync::atomic::AtomicBool::new(false);
pub fn interrupted()->bool {SIGNAL_STOP.load(std::sync::atomic::Ordering::Relaxed)}

#[derive(Clone)]
pub struct Options {
    pub device:usize,pub worksize:usize,pub batch:usize,pub seconds:u64,pub threads:usize,
    pub unroll:bool,pub pool:String,pub user:String,pub debug:bool,pub log:Option<String>,
    pub stop_accepted:u64,pub mine_seconds:u64,
    pub node:String,pub min_height:u64,
    pub max_power:Option<f64>,pub power_limit:Option<f64>,pub power_percent:Option<i32>,
    pub core_clock:Option<u32>,pub memory_clock:Option<u32>,pub fan:Option<u8>,pub intensity:u8,
    pub max_temp:Option<i32>,pub max_hotspot:Option<i32>,pub stats_file:Option<String>,
    pub nonce_base:Option<u64>,pub nonce_lane:usize,pub nonce_lanes:usize,pub chain_state:Option<String>,
}
fn options()->Result<(Options,String),String>{
    let total=std::thread::available_parallelism().map(|n|n.get()).unwrap_or(1);
    let mut o=Options{device:0,worksize:128,batch:16777216,seconds:10,threads:if total>=8{total-2}else{total.saturating_sub(1).max(1)},
        unroll:true,pool:String::new(),user:String::new(),debug:false,log:None,stop_accepted:0,mine_seconds:0,
        node:"http://127.0.0.1:24002".into(),min_height:23214,
        max_power:None,power_limit:None,power_percent:None,core_clock:None,memory_clock:None,fan:None,intensity:100,
        max_temp:None,max_hotspot:None,stats_file:None,nonce_base:None,nonce_lane:0,nonce_lanes:1,chain_state:None};
    let mut mode="solo".to_string();let mut args=std::env::args().skip(1);
    while let Some(a)=args.next(){match a.as_str(){
        "--benchmark"=>mode="benchmark".into(),"--gpu-benchmark"=>mode="gpu-benchmark".into(),"--tune"=>mode="tune".into(),"--self-test"=>mode="test".into(),
        "--list-devices"=>mode="list".into(),"--list-devices-json"=>mode="list-json".into(),"--chain-watch"=>mode="chain-watch".into(),"--help"|"-h"=>mode="help".into(),"--debug"=>o.debug=true,
        "--solo"=>mode="solo".into(),"--validate-address"=>mode="validate-address".into(),
        _=>{let v=args.next().ok_or(format!("Missing value for {a}"))?;match a.as_str(){
            "--device"=>o.device=v.parse().map_err(|_|"Bad device")?,
            "--worksize"=>o.worksize=v.parse().map_err(|_|"Bad worksize")?,
            "--batch"=>o.batch=v.parse().map_err(|_|"Bad batch")?,
            "--seconds"=>o.seconds=v.parse().map_err(|_|"Bad seconds")?,
            "--cpu-threads"=>o.threads=v.parse().map_err(|_|"Bad thread count")?,
            "--unroll"=>o.unroll=match v.as_str(){"0"=>false,"1"=>true,_=>return Err("unroll is 0 or 1".into())},
            "--max-power"=>o.max_power=Some(v.parse().map_err(|_|"Bad max-power")?),
            "--power-limit"=>o.power_limit=Some(v.parse().map_err(|_|"Bad power-limit")?),
            "--power-percent"=>o.power_percent=Some(v.parse().map_err(|_|"Bad power-percent")?),
            "--core-clock"=>o.core_clock=Some(v.parse().map_err(|_|"Bad core-clock")?),
            "--memory-clock"=>o.memory_clock=Some(v.parse().map_err(|_|"Bad memory-clock")?),
            "--fan"=>o.fan=Some(v.parse().map_err(|_|"Bad fan percent")?),
            "--intensity"=>o.intensity=v.parse().map_err(|_|"Bad intensity")?,
            "--max-temp"=>o.max_temp=Some(v.parse().map_err(|_|"Bad max-temp")?),
            "--max-hotspot"=>o.max_hotspot=Some(v.parse().map_err(|_|"Bad max-hotspot")?),
            "--stats-file"=>o.stats_file=Some(v),
            "--chain-state"=>o.chain_state=Some(v),
            "--nonce-base"=>o.nonce_base=Some(v.parse().map_err(|_|"Bad nonce-base")?),
            "--nonce-lane"=>o.nonce_lane=v.parse().map_err(|_|"Bad nonce-lane")?,
            "--nonce-lanes"=>o.nonce_lanes=v.parse().map_err(|_|"Bad nonce-lanes")?,
            "--pool"=>return Err("Q-BTC pool support removed; use --solo --node http://127.0.0.1:24002".into()),"--user"=>o.user=v,"--log-file"=>o.log=Some(v),
            "--stop-after-accepted"=>o.stop_accepted=v.parse().map_err(|_|"Bad acceptance limit")?,
            "--mine-seconds"=>o.mine_seconds=v.parse().map_err(|_|"Bad runtime")?,
            "--node"=>o.node=v,"--min-height"=>o.min_height=v.parse().map_err(|_|"Bad minimum height")?,
            _=>return Err(format!("Unknown option {a}")),
        }}
    }}
    if ![64,128,256].contains(&o.worksize)||o.batch==0||o.batch%(o.worksize*2)!=0||o.batch>16777216{
        return Err("worksize must be 64/128/256; batch must be divisible by 2 * worksize and <=16777216".into());}
    if o.seconds==0||o.threads==0{return Err("seconds and cpu-threads must be positive".into());}
    if o.nonce_lanes==0||o.nonce_lanes>256||o.nonce_lane>=o.nonce_lanes{return Err("Invalid nonce lane assignment".into());}
    if o.nonce_lanes>1&&o.nonce_base.is_none(){return Err("Multi-GPU nonce lanes require a common --nonce-base".into());}
    if !(1..=100).contains(&o.intensity)||o.fan.is_some_and(|v|v>100)||o.max_power.is_some_and(|v|!v.is_finite()||v<=0.)||o.power_limit.is_some_and(|v|!v.is_finite()||v<=0.)||o.max_temp.is_some_and(|v|!(40..=100).contains(&v))||o.max_hotspot.is_some_and(|v|!(40..=105).contains(&v)) {return Err("Invalid GPU limits".into());}
    Ok((o,mode))
}
pub fn hex(bytes:&[u8])->String{bytes.iter().map(|b|format!("{b:02x}")).collect()}
fn test_header(seed:u8)->[u8;120]{
    let mut h=[0u8;120];for(i,b)in h.iter_mut().enumerate(){*b=(i as u8).wrapping_mul(37).wrapping_add(seed);}h
}
fn evidence(name:&str,value:&serde_json::Value)->Result<(),String>{
    std::fs::create_dir_all("evidence").map_err(|e|e.to_string())?;
    std::fs::write(format!("evidence/{name}"),serde_json::to_string_pretty(value).unwrap()).map_err(|e|e.to_string())
}
fn self_test(gpu:&opencl::Gpu,wg:usize)->Result<(),String>{
    let mut count=0;let mut vectors=Vec::new();
    for seed in [0u8,7,255]{
        let mut header=test_header(seed);gpu.set_job(&header)?;
        for base in [0u64,0xffffff00,0xffffffffffffff00,0x0123456789abcdef]{
            let n=1024;let hashes=gpu.digests(base,n,wg)?;
            for(i,hash)in hashes.iter().enumerate(){let nonce=base.wrapping_add(i as u64);
                header[104..112].copy_from_slice(&nonce.to_be_bytes());let cpu=pow::hash_header(&header);
                if cpu!=*hash{return Err(format!("CPU/GPU digest mismatch nonce={nonce} seed={seed}"));}
                count+=1;if i==0||i==255||i==256{vectors.push(json!({"header":hex(&header),"nonce":nonce,"digest":hex(hash)}));}
            }
        }
        let hashes=gpu.digests(0,1024,wg)?;
        let boundary=u64::from_be_bytes(hashes[5][..8].try_into().unwrap());
        for target in [0,u64::MAX,boundary,boundary.saturating_sub(1)]{
            let(mut found,_)=gpu.search(0,target,1024,wg)?;found.sort_unstable();
            let expected:Vec<u64>=hashes.iter().enumerate().filter(|(_,h)|pow::meets_target(h,target)).map(|(i,_)|i as u64).collect();
            if found!=expected{return Err(format!("GPU target filter mismatch target={target}"));}
        }
    }
    evidence("vectors.json",&json!({"core_commit":"5797e6f4dbc162d698e8f897853db0011813dd96","algorithm":"SHA256(header120)","vectors":vectors}))?;
    evidence("correctness.json",&json!({"gpu":gpu.name,"driver":gpu.driver,"digest_comparisons":count,
        "worksize":wg,"target_filter_tests":12,"errors":0,"kernel":gpu.kernel_info}))?;
    println!("CPU/GPU bit-exact: PASS ({count} digests, 12 target/boundary tests, worksize={wg})");Ok(())
}
fn cpu_bench(seconds:u64,threads:usize)->(f64,u64){
    let barrier=Arc::new(Barrier::new(threads+1));let mut handles=Vec::new();
    for t in 0..threads{let b=barrier.clone();handles.push(std::thread::spawn(move||{
        let mut h=test_header(7);let mut nonce=(t as u64)<<48;let mut count=0u64;let mut checksum=0u8;
        b.wait();let start=Instant::now();while !interrupted() && start.elapsed()<Duration::from_secs(seconds){
            for _ in 0..8192{h[104..112].copy_from_slice(&nonce.to_be_bytes());
                let digest=std::hint::black_box(pow::hash_header(std::hint::black_box(&h)));
                checksum^=digest[0];std::hint::black_box(pow::meets_target(&digest,0));nonce=nonce.wrapping_add(1);}
            count+=8192;
        }std::hint::black_box(checksum);count
    }));}
    barrier.wait();let start=Instant::now();let hashes=handles.into_iter().map(|h|h.join().unwrap()).sum::<u64>();
    (hashes as f64/start.elapsed().as_secs_f64(),hashes)
}
fn gpu_bench(gpu:&opencl::Gpu,o:&Options)->Result<serde_json::Value,String>{
    let telemetry=telemetry::Telemetry::new(&gpu.identity);
    let mut controls=gpu_control::Monitor::new(&gpu.identity,o)?;
    gpu.set_job(&test_header(7))?;if controls.ready(){gpu.search(0,0,o.batch,o.worksize)?;}
    let start=Instant::now();let mut total=0u64;let mut kernel_seconds=0f64;let mut launches=0u64;
    let mut sampled=Instant::now();let mut samples=Vec::new();
    while !interrupted() && start.elapsed()<Duration::from_secs(o.seconds){if !controls.ready(){std::thread::sleep(Duration::from_millis(50));continue;}let dispatched=Instant::now();let(_,k)=gpu.search(total,0,o.batch,o.worksize)?;kernel_seconds+=k;total+=o.batch as u64;launches+=1;controls.after_dispatch(dispatched.elapsed());
        if sampled.elapsed()>=Duration::from_millis(500){if let Some(t)=&telemetry{if let Some(r)=t.read(){samples.push(json!({"seconds":start.elapsed().as_secs_f64(),"asic_power_w":r.power,"temperature_c":r.temperature,"utilization_percent":r.utilization}));}}sampled=Instant::now();}}
    let elapsed=start.elapsed().as_secs_f64();let speed=total as f64/elapsed;
    let powers:Vec<f64>=samples.iter().filter_map(|s|s["asic_power_w"].as_f64()).collect();
    let power=if powers.is_empty(){None}else{Some(powers.iter().sum::<f64>()/powers.len() as f64)};
    println!("GPU {}: {:.3} MH/s; worksize={} unroll={} kernel={:.3} ms",gpu.name,speed/1e6,o.worksize,o.unroll,kernel_seconds*1000.0/launches as f64);
    println!("ASIC power (ADL): {}",power.map(|p|format!("{p:.1} W")).unwrap_or_else(||"unavailable".into()));
    Ok(json!({"gpu":gpu.name,"driver":gpu.driver,"worksize":o.worksize,"batch":o.batch,"unroll":o.unroll,
        "hashes":total,"wall_seconds":elapsed,"hashrate":speed,"kernel_hashrate":total as f64/kernel_seconds,
        "average_kernel_ms":kernel_seconds*1000.0/launches as f64,"kernel_info":gpu.kernel_info,"asic_power_w":power,
        "telemetry_gpu":telemetry.as_ref().map(|t|&t.name),"telemetry_samples":samples}))
}
fn run()->Result<(),String>{
    ctrlc::set_handler(||SIGNAL_STOP.store(true,std::sync::atomic::Ordering::Relaxed)).map_err(|e|e.to_string())?;
    let(o,mode)=options()?;if mode=="help"{println!("lackminer-qbtc --list-devices | --self-test | --benchmark | --tune\n--device 0 --worksize 128 --batch 16777216 --unroll 1 --seconds 10 --cpu-threads N\n--solo --node http://127.0.0.1:24002 --user QBTC_ADDRESS --debug --log-file PATH\n--stop-after-accepted N --mine-seconds N\n--max-power W --power-limit W --power-percent P --core-clock MHZ --memory-clock MHZ\n--fan PERCENT --intensity 1..100 --max-temp C --max-hotspot C --stats-file PATH");return Ok(());}
    if mode=="validate-address"{solo::validate_address(&o.user)?;println!("Q-BTC payout address valid");return Ok(());}
    if mode=="list"{return opencl::list();}
    if mode=="list-json"{return opencl::list_json();}
    if mode=="chain-watch"{return solo::watch_chain(&o);}
    if mode=="tune"{
        let mut rows=Vec::new();for unroll in [false,true]{let gpu=opencl::Gpu::new(o.device,unroll)?;
            for wg in [64,128,256]{let mut trial=o.clone();trial.worksize=wg;trial.unroll=unroll;
                self_test(&gpu,wg)?;rows.push(gpu_bench(&gpu,&trial)?);}}
        evidence("tuning.json",&json!(rows))?;return Ok(());
    }
    let gpu=opencl::Gpu::new(o.device,o.unroll)?;println!("lackminer qbtc v{} | {} | {}",env!("CARGO_PKG_VERSION"),gpu.name,gpu.driver);
    self_test(&gpu,o.worksize)?;
    if mode=="test"{return Ok(());}
    if mode=="gpu-benchmark"{
        let g=gpu_bench(&gpu,&o)?;
        evidence("benchmark.json",&json!({"gpu":g,"errors":0,"cpu_gpu_selftest":"PASS"}))?;
        return Ok(());
    }
    if mode=="benchmark"{
        let(cpu,hashes)=cpu_bench(o.seconds,o.threads);println!("CPU ({} threads, upstream full-header loop): {:.3} MH/s",o.threads,cpu/1e6);
        if interrupted(){return Ok(());}
        let g=gpu_bench(&gpu,&o)?;let speed=g["hashrate"].as_f64().unwrap();println!("GPU/CPU: {:.2}x",speed/cpu);
        evidence("benchmark.json",&json!({"cpu_hashrate":cpu,"cpu_hashes":hashes,"cpu_threads":o.threads,
            "cpu_model":std::env::var("PROCESSOR_IDENTIFIER").ok(),"gpu":g,"speedup":speed/cpu,"errors":0}))?;return Ok(());
    }
    if o.user.is_empty(){return Err("--user QBTC_ADDRESS is required".into());}
    if mode=="solo"{return solo::mine(o,gpu);}
    Err("Only SOLO mining is supported".into())
}
fn main(){if let Err(e)=run(){eprintln!("ERROR: {e}");std::process::exit(1);}}
