
use super::{get_template, decode32};
use crate::{pow,hex};
use serde_json::{json,Value};
use std::{sync::{Arc,Mutex,atomic::{AtomicBool,Ordering}},time::{Duration,Instant}};

#[derive(Default)]
struct Observation { tip_height:u64, tip_hash:String, checked:Option<Instant>, error:Option<String> }
pub struct ChainGuard { state:Arc<Mutex<Observation>> }

fn rejoin_ready(checks:&mut u8)->bool {
    if *checks==0 {true} else {*checks-=1;false}
}

fn fetch(client:&reqwest::blocking::Client,path:&str,body:Option<Value>)->Result<Value,String> {
    
    
    
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
        .map_err(|e|e.to_string())?.as_nanos();
    let url=format!("https://explorer.qbtc-core.org/api/{path}?_={stamp}");
    let request=if let Some(body)=body {client.post(url).json(&body)} else {client.get(url)};
    let request=request.header("Cache-Control","no-cache").header("Pragma","no-cache");
    request.send().and_then(|r|r.error_for_status()).and_then(|r|r.json())
        .map_err(|e|format!("Independent chain check unavailable: {e}"))
}
fn observed_hash(block:&Value)->Result<String,String>{
    let timestamp=block["timestamp"].as_u64().ok_or("Missing timestamp")?;
    let previous=decode32(block["previous_hash"].as_str().ok_or("Missing parent hash")?)?;
    let merkle=decode32(block["merkle_root"].as_str().ok_or("Missing Merkle root")?)?;
    let commit=decode32(block["commit_merkle_root"].as_str().ok_or("Missing witness root")?)?;
    let nonce=block["nonce"].as_u64().ok_or("Missing nonce")?;
    let target=block["target"].as_u64().ok_or("Missing target")?;
    let hash=pow::hash_header(&pow::encode_header(timestamp,&previous,&merkle,&commit,nonce,target));
    if !pow::meets_target(&hash,target){return Err("Independent block failed PoW".into());}
    Ok(hex(&hash))
}
impl ChainGuard {
    pub fn start(url:String,address:String,stop:Arc<AtomicBool>)->Self{
        let state=Arc::new(Mutex::new(Observation::default()));let worker=state.clone();
        std::thread::spawn(move||{
            let client=match reqwest::blocking::Client::builder().timeout(Duration::from_secs(3)).no_proxy().build(){Ok(c)=>c,Err(_)=>return};
            let remote=match reqwest::blocking::Client::builder().connect_timeout(Duration::from_secs(2))
                .timeout(Duration::from_secs(4)).redirect(reqwest::redirect::Policy::none()).build(){Ok(c)=>c,Err(_)=>return};
            let mut anchor:Option<(u64,String)>=None;
            let mut rejoin_checks=0u8;
            while !stop.load(Ordering::Relaxed){
                let result=(||{
                    let t=get_template(&client,&url,&address)?.ok_or("Local template unavailable")?;
                    let height=t.current_height.checked_sub(1).ok_or("Missing parent")?;
                    let remote_info=fetch(&remote,"get_info",None)?;
                    let remote_height=remote_info["current_height"].as_u64().ok_or("Missing independent height")?;
                    if remote_height!=height {return Err(format!("Local tip {height}, independent tip {remote_height}; waiting for equal tips"));}
                    let block=fetch(&remote,"get_block",Some(json!({"height":height})))?;
                    let hash=observed_hash(&block)?;
                    if hash!=t.previous_hash {return Err(format!("Conflicting parent hashes at height {height}"));}
                    if let Some((old_height,old_hash))=&anchor {
                        let same_anchor=if *old_height==height {hash==*old_hash}
                            else if *old_height>height {false}
                            else {observed_hash(&fetch(&remote,"get_block",Some(json!({"height":old_height})))?)?==*old_hash};
                        if !same_anchor {
                            println!("CHAIN GUARD: reorganization at {old_height}; revalidating the synchronized branch before resuming");
                            rejoin_checks=3;
                        }
                    }
                    anchor=Some((height,hash.clone()));
                    if !rejoin_ready(&mut rejoin_checks) {
                        return Err("Reorganization: confirming local/public branch agreement".into());
                    }
                    Ok((height,hash))
                })();
                {
                    let mut s=worker.lock().unwrap();
                    match result {
                        Ok((height,hash))=>{s.tip_height=height;s.tip_hash=hash;s.checked=Some(Instant::now());s.error=None;},
                        
                        
                        Err(e) if e.starts_with("Independent chain check unavailable") && s.checked.is_some()=>{},
                        Err(e)=>{
                            if rejoin_checks>0 && !e.starts_with("Reorganization: confirming") {rejoin_checks=3;}
                            s.checked=None;s.error=Some(e);
                        }
                    }
                }
                for _ in 0..10 {if stop.load(Ordering::Relaxed){return;}std::thread::sleep(Duration::from_millis(100));}
            }
        });
        Self{state}
    }
    pub fn safety_stop_reason(&self)->Option<String>{
        self.state.lock().unwrap().error.clone().filter(|e|e.starts_with("Verified chain reorganized"))
    }
    pub fn permits(&self,work_height:u64,parent:&str)->Result<(),String>{
        let s=self.state.lock().unwrap();
        if let Some(e)=&s.error{return Err(e.clone());}
        let checked=s.checked.ok_or("Waiting for independent chain observation")?;
        if checked.elapsed()>Duration::from_secs(10){return Err("Independent observation older than 10 seconds".into());}
        if work_height.checked_sub(1)!=Some(s.tip_height) || parent!=s.tip_hash {
            return Err("New parent not yet observed on independent node".into());
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]fn reorganization_requires_three_new_matching_observations(){
        let mut checks=3;
        assert!(!rejoin_ready(&mut checks));assert!(!rejoin_ready(&mut checks));assert!(!rejoin_ready(&mut checks));
        assert!(rejoin_ready(&mut checks));
    }
    #[test]fn safety_stop_is_distinct_from_temporary_observation_failure(){
        let state=Arc::new(Mutex::new(Observation::default()));let g=ChainGuard{state:state.clone()};
        state.lock().unwrap().error=Some("Independent chain check unavailable".into());
        assert!(g.safety_stop_reason().is_none());
        state.lock().unwrap().error=Some("Verified chain reorganized; automatic continuation disabled".into());
        assert!(g.safety_stop_reason().is_some());
    }
    #[test]fn blocks_unknown_and_conflicting_parents(){
        let state=Arc::new(Mutex::new(Observation::default()));let g=ChainGuard{state:state.clone()};
        assert!(g.permits(11,"abc").is_err());
        *state.lock().unwrap()=Observation{tip_height:10,tip_hash:"abc".into(),checked:Some(Instant::now()),error:None};
        assert!(g.permits(11,"abc").is_ok());assert!(g.permits(12,"abc").is_err());assert!(g.permits(11,"def").is_err());
        state.lock().unwrap().checked=Some(Instant::now()-Duration::from_secs(11));
        assert!(g.permits(11,"abc").is_err());
    }
}
