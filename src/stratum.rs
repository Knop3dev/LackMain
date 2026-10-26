use crate::{hex,opencl::Gpu,pow,Options};
use serde_json::{json,Value};
use std::{collections::HashMap,fs::File,io::Write,sync::{Arc,RwLock,atomic::{AtomicBool,AtomicU64,Ordering}},time::{Duration,Instant}};
use tokio::{io::{AsyncBufReadExt,AsyncWriteExt,BufReader},net::TcpStream};

#[derive(Clone)]
struct Job{job_id:u64,target:u64,header:[u8;120],version:u64,range:Option<(u64,u64)>}
struct Share{job:Job,nonce:u64,digest:[u8;32]}
static ACCEPTED:AtomicU64=AtomicU64::new(0);
static REJECTED:AtomicU64=AtomicU64::new(0);
static STALE:AtomicU64=AtomicU64::new(0);
static HASHES:AtomicU64=AtomicU64::new(0);
fn decode32(v:&Value)->Result<[u8;32],String>{
    let s=v.as_str().ok_or("Expected hash hex string")?;
    if s.len()!=64||!s.bytes().all(|c|c.is_ascii_hexdigit()){return Err("Hash must have exactly 64 hex digits".into());}
    let mut out=[0u8;32];for i in 0..32{out[i]=u8::from_str_radix(&s[2*i..2*i+2],16).map_err(|e|e.to_string())?;}Ok(out)
}
fn decode_job(v:&Value,version:u64)->Result<Job,String>{
    let p=v["params"].as_array().ok_or("notify params must be array")?;if p.len()!=7&&p.len()!=9{return Err("Expected 7 or 9 notify parameters".into());}
    let number=|i:usize|p[i].as_u64().ok_or(format!("notify parameter {i} must be u64"));
    if number(6)?<number(5)?{return Err("Share target is harder than network target".into());}
    let range=if p.len()==9{let lo=number(7)?;let hi=number(8)?;if hi<=lo{return Err("Invalid nonce range".into());}Some((lo,hi))}else{None};
    Ok(Job{job_id:number(0)?,target:number(6)?,version,range,
        header:pow::encode_header(number(4)?,&decode32(&p[1])?,&decode32(&p[2])?,&decode32(&p[3])?,0,number(5)?)})
}
fn log(file:&mut Option<File>,value:Value){if let Some(f)=file {let _=writeln!(f,"{value}");let _=f.flush();}}
fn cpu_worker(o:&Options,current:Arc<RwLock<Option<Job>>>,running:Arc<AtomicBool>,hashes:Arc<AtomicU64>,tx:tokio::sync::mpsc::Sender<Result<Share,String>>)->Result<(),String>{
    let mut handles=Vec::new();
    for lane in 0..o.threads{
        let current=current.clone();let running=running.clone();let hashes=hashes.clone();let tx=tx.clone();let threads=o.threads as u64;
        handles.push(std::thread::spawn(move||{
            let mut version=0;let mut nonce=lane as u64;
            while running.load(Ordering::Relaxed)&&!crate::interrupted(){
                let job=current.read().unwrap().clone();
                let Some(job)=job else{std::thread::sleep(Duration::from_millis(20));continue;};
                if version!=job.version{version=job.version;nonce=job.range.map(|r|r.0).unwrap_or(0)+lane as u64;}
                let mut header=job.header;let mut count=0;
                for _ in 0..4096{
                    if job.range.is_some_and(|r|nonce>=r.1){break;}
                    header[104..112].copy_from_slice(&nonce.to_be_bytes());let digest=pow::hash_header(&header);count+=1;
                    if pow::meets_target(&digest,job.target)&&tx.blocking_send(Ok(Share{job:job.clone(),nonce,digest})).is_err(){return;}
                    nonce=nonce.wrapping_add(threads);
                }
                hashes.fetch_add(count,Ordering::Relaxed);
                if count==0{std::thread::sleep(Duration::from_millis(20));}
            }
        }));
    }
    println!("CPU pool mining: {} threads",o.threads);
    for handle in handles{handle.join().map_err(|_|"CPU mining worker failed")?;}
    Ok(())
}
async fn read_line_limited(reader:&mut BufReader<tokio::net::tcp::OwnedReadHalf>,line:&mut String)->Result<usize,String>{
    let mut length=0;
    loop {
        let data=reader.fill_buf().await.map_err(|e|e.to_string())?;
        if data.is_empty(){return Ok(length);}
        let end=data.iter().position(|b|*b==b'\n').map(|i|i+1).unwrap_or(data.len());
        if line.len()+end>16384{return Err("Pool message exceeds 16 KiB".into());}
        let complete=data[end-1]==b'\n';
        line.push_str(std::str::from_utf8(&data[..end]).map_err(|e|e.to_string())?);
        reader.consume(end);length+=end;if complete{return Ok(length);}
    }
}
pub async fn mine(o:Options)->Result<(),String>{
    let endpoint=o.pool.strip_prefix("stratum+tcp://").unwrap_or(&o.pool);
    if endpoint.contains('/') {return Err("Pool must be HOST:PORT or stratum+tcp://HOST:PORT".into());}
    let stream=tokio::time::timeout(Duration::from_secs(15),TcpStream::connect(endpoint)).await.map_err(|_|"Pool connect timed out")?.map_err(|e|e.to_string())?;
    stream.set_nodelay(true).map_err(|e|e.to_string())?;
    let(read,mut write)=stream.into_split();let mut reader=BufReader::new(read);
    let mut file=match &o.log{Some(p)=>Some(std::fs::OpenOptions::new().create(true).append(true).open(p).map_err(|e|e.to_string())?),None=>None};
    for req in [json!({"id":1,"method":"mining.subscribe","params":["lackminer-qbtc/0.3.0",{"device":if o.cpu{"cpu"}else{"gpu"}}]}),json!({"id":2,"method":"mining.authorize","params":[o.user,"x"]})]{
        log(&mut file,json!({"direction":"TX","message":req}));write.write_all(format!("{req}\n").as_bytes()).await.map_err(|e|e.to_string())?;}
    let base_hashes=HASHES.load(Ordering::Relaxed);
    let current=Arc::new(RwLock::new(None::<Job>));let running=Arc::new(AtomicBool::new(true));let hashes=Arc::new(AtomicU64::new(base_hashes));
    let(tx,mut rx)=tokio::sync::mpsc::channel::<Result<Share,String>>(64);
    let control_stats=Arc::new(RwLock::new(Value::Null));let worker_stats=control_stats.clone();
    let active=current.clone();let flag=running.clone();let counter=hashes.clone();let opts=o.clone();
    let worker=std::thread::spawn(move||{
        let work=(||->Result<(),String>{
            if opts.cpu{return cpu_worker(&opts,active,flag,counter,tx.clone());}
            let gpu=Gpu::new(opts.device,opts.unroll)?;crate::self_test(&gpu,opts.worksize)?;let mut version=0;
            let mut controls=crate::gpu_control::Monitor::new(&gpu.identity,&opts)?;
            let mut nonce=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos() as u64;
            while flag.load(Ordering::Relaxed)&&!crate::interrupted(){let job=active.read().unwrap().clone();
                let ready=controls.ready();*worker_stats.write().unwrap()=controls.stats();
                if !ready{std::thread::sleep(Duration::from_millis(50));continue;}
                if let Some(j)=job{
                    if j.version!=version{gpu.set_job(&j.header)?;version=j.version;if let Some((base,_))=j.range{nonce=base;}}
                    let probability=(j.target as f64+1.0)/18446744073709551616.0;
                    let safe=(4.0/probability).min(opts.batch as f64) as usize;
                    let alignment=opts.worksize*2;
                    let mut batch=(safe/alignment).max(1)*alignment;
                    if let Some((_,end))=j.range{
                        if nonce>=end{std::thread::sleep(Duration::from_millis(20));continue;}
                        batch=batch.min(((end-nonce) as usize/alignment)*alignment);
                        if batch==0{std::thread::sleep(Duration::from_millis(20));continue;}
                    }
                    let dispatched=Instant::now();
                    let(found,_)=gpu.search(nonce,j.target,batch,opts.worksize)?;
                    controls.after_dispatch(dispatched.elapsed());
                    nonce=nonce.wrapping_add(batch as u64);counter.fetch_add(batch as u64,Ordering::Relaxed);
                    for n in found{let mut h=j.header;h[104..112].copy_from_slice(&n.to_be_bytes());let digest=pow::hash_header(&h);
                        if !pow::meets_target(&digest,j.target){return Err(format!("GPU share CPU verification failed nonce={n}"));}
                        if tx.blocking_send(Ok(Share{job:j.clone(),nonce:n,digest})).is_err(){return Ok(());}
                    }
                }else{std::thread::sleep(Duration::from_millis(20));}
            }Ok(())})();if let Err(e)=work{let _=tx.blocking_send(Err(e));}
    });
    let mut pending=HashMap::<u64,Value>::new();let mut id=3u64;let mut version=0u64;let mut authorized=false;
    let(mut accepted,mut rejected,mut stale)=(ACCEPTED.load(Ordering::Relaxed),REJECTED.load(Ordering::Relaxed),STALE.load(Ordering::Relaxed));let mut line=String::new();
    let started=Instant::now();let mut tick=tokio::time::interval(Duration::from_secs(5));let mut last=Instant::now();let mut last_count=base_hashes;
    let(stop_tx,mut stop_rx)=tokio::sync::mpsc::channel::<()>(1);
    std::thread::spawn(move||{
        use std::io::BufRead;
        for line in std::io::stdin().lock().lines(){
            if line.map(|s|s.trim()=="stop").unwrap_or(false){let _=stop_tx.blocking_send(());break;}
        }
    });
    println!("Connected to {endpoint}; authorizing {}",o.user);
    let result=async {
        loop{tokio::select!{
            msg=read_line_limited(&mut reader,&mut line)=>{
                let bytes=msg.map_err(|e|e.to_string())?;if bytes==0{return Err("Pool disconnected".into());}
                let parsed:Value=serde_json::from_str(&line).map_err(|e|e.to_string())?;
                if o.debug{println!("RX {}",line.trim());}log(&mut file,json!({"direction":"RX","message":parsed}));line.clear();
                if parsed["method"]=="mining.pause"{
                    *current.write().unwrap()=None;println!("Pool paused: {}",parsed["params"][0]);
                    log(&mut file,json!({"event":"pool_paused","reason":parsed["params"][0]}));
                }else if parsed["method"]=="mining.notify"{
                    version+=1;let j=decode_job(&parsed,version)?;println!("Real Q-BTC job {} | share target {}",j.job_id,j.target);
                    log(&mut file,json!({"event":"job","job_id":j.job_id,"header":hex(&j.header),"target":j.target}));
                    if authorized{*current.write().unwrap()=Some(j);}else{return Err("notify before authorization".into());}
                }else if let Some(rid)=parsed["id"].as_u64(){
                    if rid==1&&parsed["result"].is_object(){println!("Pool fee {}%; minimum payout {} QBTC; scheme {}",parsed["result"]["fee_percent"],parsed["result"]["minimum_payout_qbtc"],parsed["result"]["payout"]);}
                    else if rid==2{if parsed["result"]!=true||!parsed["error"].is_null(){return Err(format!("Authorization rejected: {parsed}"));}authorized=true;println!("Authorized");}
                    else if let Some(proof)=pending.remove(&rid){
                        if parsed["result"]==true&&parsed["error"].is_null(){accepted+=1;println!("ACCEPTED share #{accepted} | nonce {} | CPU verified",proof["nonce"]);
                            log(&mut file,json!({"event":"accepted","request_id":rid,"proof":proof,"response":parsed}));
                        }else{rejected+=1;println!("REJECTED: {}",parsed["error"]);}
                        if o.stop_accepted>0&&accepted>=o.stop_accepted{return Ok(());}
                    }
                }
            }
            share=rx.recv()=>{
                let s=share.ok_or("GPU worker stopped")??;
                let active=current.read().unwrap().clone();if active.as_ref().map(|j|j.version)!=Some(s.job.version){stale+=1;continue;}
                let request=json!({"id":id,"method":"mining.submit","params":[o.user,s.job.job_id,s.nonce]});
                let proof=json!({"job_id":s.job.job_id,"nonce":s.nonce,"header":hex(&s.job.header),"digest":hex(&s.digest),"target":s.job.target,"cpu_verified":true});
                log(&mut file,json!({"direction":"TX","message":request,"proof":proof}));
                if o.debug{println!("TX {request}");}
                write.write_all(format!("{request}\n").as_bytes()).await.map_err(|e|e.to_string())?;pending.insert(id,proof);id+=1;
            }
            _=tick.tick()=>{
                let count=hashes.load(Ordering::Relaxed);let rate=(count-last_count) as f64/last.elapsed().as_secs_f64();last_count=count;last=Instant::now();
                println!("{} {:.3} MH/s | Accepted {accepted} | Rejected {rejected} | Stale {stale}",if o.cpu{"CPU"}else{"OpenCL"},rate/1e6);
                let stats=json!({"event":"stats","hashrate":rate,"hashes":count,"accepted":accepted,
                    "rejected":rejected,"stale":stale,"elapsed_seconds":started.elapsed().as_secs_f64(),"pending":pending.len(),"controls":control_stats.read().unwrap().clone(),"backend":if o.cpu{"CPU"}else{"OpenCL"},"updated_at":std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_secs()});
                if let Some(path)=&o.stats_file{let path=std::path::Path::new(path);let temporary=path.with_extension("tmp");if std::fs::write(&temporary,stats.to_string()).is_ok(){let _=std::fs::rename(temporary,path);}}
                log(&mut file,stats);
                if crate::interrupted(){return Ok(());}
                if o.mine_seconds>0&&started.elapsed()>=Duration::from_secs(o.mine_seconds){return Ok(());}
            }
            Some(())=stop_rx.recv()=>{return Ok(());}
        }}
    }.await;
    running.store(false,Ordering::Relaxed);rx.close();drop(rx);
    let _=tokio::task::spawn_blocking(move||worker.join()).await;
    ACCEPTED.store(accepted,Ordering::Relaxed);REJECTED.store(rejected,Ordering::Relaxed);STALE.store(stale,Ordering::Relaxed);HASHES.store(hashes.load(Ordering::Relaxed),Ordering::Relaxed);
    let summary=json!({"event":"summary","pool":o.pool,"accepted":accepted,"rejected":rejected,"stale":stale,
        "hashes":hashes.load(Ordering::Relaxed),"seconds":started.elapsed().as_secs_f64(),"pending":pending.len()});
    println!("{summary}");log(&mut file,summary);result
}

#[cfg(test)]
mod tests{
    use super::*;
    #[test] fn official_job_preserves_network_target_not_share_target(){
        let v=json!({"params":[42,"00".repeat(32),"11".repeat(32),"22".repeat(32),17,123,456]});
        let j=decode_job(&v,1).unwrap();assert_eq!(j.target,456);assert_eq!(&j.header[112..120],&123u64.to_be_bytes());
        assert_eq!(&j.header[..8],&17u64.to_be_bytes());assert_eq!(j.job_id,42);
    }
    #[test] fn malformed_hash_is_rejected(){assert!(decode32(&json!("z".repeat(64))).is_err());assert!(decode32(&json!("00")).is_err());}
}
