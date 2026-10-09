

use crate::{hex, opencl::Gpu, pow, Options};
use bech32::{FromBase32, Variant};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{fs::File, io::Write, sync::{Arc, atomic::{AtomicBool, Ordering}},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH}};


pub const DEVELOPER_FEE_BPS:u64=1_000;
pub const DEVELOPER_ADDRESS:&str="qbtc10y29nvfuwyxfxhkl4yqkenw4u6hshsk9zgaf5ctz4zfpa2gxe45qtwawce";
#[path = "merkle.rs"]
#[allow(dead_code)]
mod merkle;

#[path = "chain_guard.rs"]
mod chain_guard;

#[derive(Clone, Serialize, Deserialize)]
struct Input { previous_output_hash: [u8;32], vout: u32 }
#[derive(Clone, Serialize, Deserialize)]
struct Recovery { recovery_hash: [u8;32], recovery_delay: u64 }
#[derive(Clone, Serialize, Deserialize)]
struct Output { value: u64, public_key_hash: [u8;32], recovery: Option<Recovery> }
#[derive(Clone, Serialize, Deserialize)]
struct Witness { signature: Vec<u8>, public_key: Vec<u8> }
#[derive(Clone, Serialize, Deserialize)]
struct Transaction { inputs: Vec<Input>, outputs: Vec<Output>, witnesses: Vec<Witness> }
#[derive(Clone, Serialize, Deserialize)]
struct Header { timestamp: u64, previous_hash: [u8;32], merkle_root: [u8;32],
    commit_merkle_root: [u8;32], nonce: u64, target: u64 }
#[derive(Clone, Serialize, Deserialize)]
struct Block { header: Header, transactions: Vec<Transaction> }
#[derive(Clone, Deserialize)]
struct Template { previous_hash: String, current_height: u64, target: u64, transactions: Vec<Transaction> }
#[derive(Clone,Copy,Debug)]
struct RewardSplit { total:u64, miner:u64, developer:u64 }

fn decode32(s: &str) -> Result<[u8;32],String> {
    if s.len()!=64 || !s.bytes().all(|c|c.is_ascii_hexdigit()){return Err("Expected 32-byte hex".into());}
    let mut out=[0u8;32];for i in 0..32 {out[i]=u8::from_str_radix(&s[i*2..i*2+2],16).map_err(|e|e.to_string())?;}Ok(out)
}
fn payout_hash(address: &str) -> Result<[u8;32],String> {
    let (hrp,data,variant)=bech32::decode(address).map_err(|e|e.to_string())?;
    if hrp!="qbtc" || variant!=Variant::Bech32m {return Err("Expected Q-BTC Bech32m address".into());}
    let bytes=Vec::<u8>::from_base32(&data).map_err(|e|e.to_string())?;
    bytes.try_into().map_err(|_|"Q-BTC address must contain 32 bytes".into())
}
pub fn validate_address(address: &str) -> Result<(),String> { payout_hash(address).map(|_|()) }
impl Block {
    fn pow_header(&self)->[u8;120]{let h=&self.header;
        pow::encode_header(h.timestamp,&h.previous_hash,&h.merkle_root,&h.commit_merkle_root,h.nonce,h.target)}
}
fn assemble(template: &Template, address: &str, timestamp: u64)->Result<(Block,RewardSplit),String> {
    let recipient=payout_hash(address)?;
    let developer=payout_hash(DEVELOPER_ADDRESS)?;
    let coinbase=template.transactions.first().ok_or("Empty node template")?;
    if coinbase.inputs.len()!=1 || coinbase.inputs[0].previous_output_hash!=[0;32]
        || u64::from(coinbase.inputs[0].vout)!=template.current_height
        || coinbase.outputs.len()!=1 || coinbase.outputs[0].public_key_hash!=recipient
        || coinbase.outputs[0].recovery.is_some() {
        return Err("Refusing template: expected the node coinbase to pay only --user before fee split".into());
    }
    let subsidy=5_000_000_000u64.checked_shr((template.current_height/210000).min(64) as u32).unwrap_or(0);
    let total=coinbase.outputs[0].value;
    if total<subsidy {return Err("Coinbase reward below official subsidy".into());}
    let developer_fee=total.checked_mul(DEVELOPER_FEE_BPS).ok_or("Coinbase fee overflow")?/10_000;
    let miner_amount=total.checked_sub(developer_fee).ok_or("Invalid developer fee")?;
    let split=RewardSplit{total,miner:miner_amount,developer:developer_fee};
    let mut template_transactions=template.transactions.clone();
    if developer!=recipient && developer_fee>0 {
        template_transactions[0].outputs[0].value=miner_amount;
        template_transactions[0].outputs.push(Output{value:developer_fee,public_key_hash:developer,recovery:None});
    }
    let mut txids=Vec::new();let mut witnesses=Vec::new();let mut transactions=Vec::new();
    let mut seen=std::collections::HashSet::new();
    for tx in &template_transactions {
        let id:[u8;32]=Sha256::digest(bincode::serialize(&(&tx.inputs,&tx.outputs)).map_err(|e|e.to_string())?).into();
        if seen.insert(id) {
            txids.push(id);
            witnesses.push(Sha256::digest(bincode::serialize(tx).map_err(|e|e.to_string())?).into());
            transactions.push(tx.clone());
        }
    }
    Ok((Block { header:Header{timestamp,previous_hash:decode32(&template.previous_hash)?,
        merkle_root:merkle::build_merkle_root(txids),commit_merkle_root:merkle::build_merkle_root(witnesses),
        nonce:0,target:template.target},transactions },split))
}
static STATS_PATH:std::sync::OnceLock<std::path::PathBuf>=std::sync::OnceLock::new();
fn emit(file: &mut Option<File>, mut event: Value){
    event["version"]=json!(env!("CARGO_PKG_VERSION"));
    event["updated_at"]=json!(SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs());
    if event["event"]=="stats" {if let Some(path)=STATS_PATH.get(){let temp=path.with_extension("tmp");if std::fs::write(&temp,event.to_string()).is_ok(){let _=std::fs::rename(temp,path);}}}
    if let Some(f)=file {let _=writeln!(f,"{event}");let _=f.flush();}
}
fn node_url(s: &str)->Result<reqwest::Url,String>{
    let u=reqwest::Url::parse(s).map_err(|e|e.to_string())?;
    if u.scheme()!="http" || !matches!(u.host_str(),Some("127.0.0.1"|"localhost"|"[::1]"))
        || !u.username().is_empty() || u.password().is_some() || u.path()!="/" || u.query().is_some(){
        return Err("SOLO requires a direct loopback http://HOST:PORT node".into());}
    Ok(u)
}
fn get_template(client:&reqwest::blocking::Client,url:&str,address:&str)->Result<Option<Template>,String>{
    client.post(format!("{url}/api/get_block_template")).json(&json!({"miner_address":address}))
        .send().and_then(|r|r.error_for_status()).and_then(|r|r.json()).map_err(|e|e.to_string())
}
pub fn watch_chain(o:&Options)->Result<(),String>{
    node_url(&o.node)?;validate_address(&o.user)?;
    let path=std::path::PathBuf::from(o.chain_state.as_ref().ok_or("--chain-state is required for --chain-watch")?);
    if let Some(parent)=path.parent(){if !parent.as_os_str().is_empty(){std::fs::create_dir_all(parent).map_err(|e|e.to_string())?;}}
    let stop=Arc::new(AtomicBool::new(false));
    let guard=chain_guard::ChainGuard::start(o.node.trim_end_matches('/').into(),o.user.clone(),stop.clone());
    let result=(||{while !crate::interrupted(){
        let temp=path.with_extension("tmp");
        std::fs::write(&temp,serde_json::to_vec(&guard.snapshot()).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
        std::fs::rename(temp,&path).map_err(|e|e.to_string())?;
        std::thread::sleep(Duration::from_millis(200));
    }Ok(())})();
    stop.store(true,Ordering::Relaxed);result
}
pub fn mine(o:Options,gpu:Gpu)->Result<(),String>{
    node_url(&o.node)?;payout_hash(&o.user)?;
    if let Some(path)=&o.stats_file {let p=std::path::PathBuf::from(path);if let Some(parent)=p.parent(){if !parent.as_os_str().is_empty(){std::fs::create_dir_all(parent).map_err(|e|e.to_string())?;}}let _=STATS_PATH.set(p);}
    let url=o.node.trim_end_matches('/');
    let client=reqwest::blocking::Client::builder().timeout(Duration::from_secs(5)).no_proxy()
        .redirect(reqwest::redirect::Policy::none()).build().map_err(|e|e.to_string())?;
    let relay=reqwest::blocking::Client::builder().connect_timeout(Duration::from_secs(2))
        .timeout(Duration::from_secs(4)).redirect(reqwest::redirect::Policy::none()).build().map_err(|e|e.to_string())?;
    let mut file=match &o.log {Some(p)=>Some(std::fs::OpenOptions::new().create(true).append(true).open(p).map_err(|e|e.to_string())?),None=>None};
    let stop=Arc::new(AtomicBool::new(false));let flag=stop.clone();
    std::thread::spawn(move||{use std::io::BufRead;for line in std::io::stdin().lock().lines(){
        if line.map(|s|s.trim()=="stop").unwrap_or(false){flag.store(true,Ordering::Relaxed);break;}}
        
        
    });
    let mut controls=crate::gpu_control::Monitor::new(&gpu.identity,&o)?;
    let guard=match &o.chain_state {Some(path)=>chain_guard::ChainGuard::follow(path.into(),stop.clone()),None=>chain_guard::ChainGuard::start(url.to_string(),o.user.clone(),stop.clone())};
    let start=Instant::now();let mut last=Instant::now();let mut last_count=0u64;
    let(mut count,mut accepted,mut rejected,mut stale)=(0u64,0u64,0u64,0u64);
    let mut compute_seconds=0.0f64;
    let clock=SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos() as u64;
    let mut ranges=crate::nonce::Ranges::new(o.nonce_base.unwrap_or(clock),o.batch,o.nonce_lane,o.nonce_lanes);
    if o.nonce_lanes>1{ranges.start_at(clock);}
    let mut active:Option<(Template,Block,RewardSplit)>=None;
    let mut next_poll=Instant::now();
    let mut guard_notice=Instant::now()-Duration::from_secs(10);
    
    println!("SOLO local node {url} | payout {} | developer fee {}% of full coinbase to {}",
        o.user,DEVELOPER_FEE_BPS as f64/100.0,DEVELOPER_ADDRESS);
    emit(&mut file,json!({"event":"solo_start","node":url,"payout_address":o.user,
        "developer_fee_bps":DEVELOPER_FEE_BPS,"developer_fee_address":DEVELOPER_ADDRESS,
        "developer_fee_basis":"entire coinbase reward (subsidy plus transaction fees)"}));
    while !crate::interrupted() && !stop.load(Ordering::Relaxed) && (o.mine_seconds==0 || start.elapsed().as_secs()<o.mine_seconds) {
        controls.ready();
        if Instant::now()>=next_poll {
            next_poll=Instant::now()+Duration::from_millis(1500);
            match get_template(&client,url,&o.user) {
                Ok(Some(t)) if t.current_height>=o.min_height=>{
                    let timestamp=SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
                    let (b,split)=assemble(&t,&o.user,timestamp)?;
                    let replace=active.as_ref().map(|(old,block,_)| old.current_height!=t.current_height ||
                        block.header.previous_hash!=b.header.previous_hash || block.header.merkle_root!=b.header.merkle_root ||
                        block.header.commit_merkle_root!=b.header.commit_merkle_root || block.header.target!=b.header.target).unwrap_or(true);
                    if replace {
                        gpu.set_job(&b.pow_header())?;
                        println!("SOLO job {} | target {} | total {:.8} QBTC | miner {:.8} | dev fee {:.8} QBTC to {}",
                            t.current_height,t.target,split.total as f64/1e8,split.miner as f64/1e8,
                            split.developer as f64/1e8,DEVELOPER_ADDRESS);
                        emit(&mut file,json!({"event":"job","job_id":t.current_height,"header":hex(&b.pow_header()),
                            "target":t.target,"payout_address":o.user,"reward_sats":split.total,
                            "miner_payout_sats":split.miner,"developer_fee_sats":split.developer,
                            "developer_fee_bps":DEVELOPER_FEE_BPS,"developer_fee_address":DEVELOPER_ADDRESS}));
                        active=Some((t,b,split));
                    }
                },
                Ok(_)=>{active=None;println!("Waiting for node synchronization (minimum height {})",o.min_height);},
                Err(e)=>{active=None;println!("Waiting for local node: {e}");}
            }
        }
        if let Some((template,block,split))=&active {
            if let Err(reason)=guard.permits(template.current_height,&template.previous_hash) {
                if guard_notice.elapsed()>=Duration::from_secs(5) {
                    println!("CHAIN GUARD PAUSED: {reason}");
                    emit(&mut file,json!({"event":"chain_guard","ready":false,"reason":reason,"height":template.current_height}));
                    emit(&mut file,json!({"event":"stats","hashrate":0,"hashes":count,"accepted":accepted,"rejected":rejected,"stale":stale,"elapsed_seconds":start.elapsed().as_secs_f64(),"pending":0,"chain_guard_paused":true,"controls":controls.stats(),"gpu_pci":gpu.identity.pci}));
                    last=Instant::now();last_count=count;
                    guard_notice=Instant::now();
                }
                std::thread::sleep(Duration::from_millis(100));
                continue;
            }
            if !controls.ready(){
                if last.elapsed()>=Duration::from_secs(5){
                    let rate=(count-last_count) as f64/last.elapsed().as_secs_f64();last=Instant::now();last_count=count;
                    println!("GPU {} | {:.3} MH/s | power {:?} W",controls.phase,rate/1e6,controls.reading.and_then(|r|r.power));
                    emit(&mut file,json!({"event":"stats","hashrate":rate,"hashes":count,"accepted":accepted,"rejected":rejected,"stale":stale,"elapsed_seconds":start.elapsed().as_secs_f64(),"controls":controls.stats(),"gpu_pci":gpu.identity.pci}));
                }
                std::thread::sleep(Duration::from_millis(50));continue;
            }
            let dispatch_start=Instant::now();
            let nonce=ranges.next().ok_or("Nonce lane exhausted")?;
            let (found,_)=gpu.search(nonce,block.header.target,o.batch,o.worksize)?;
            compute_seconds+=dispatch_start.elapsed().as_secs_f64();
            controls.after_dispatch(dispatch_start.elapsed());
            count+=o.batch as u64;
            for n in found {
                let mut candidate=block.clone();candidate.header.nonce=n;
                let digest=pow::hash_header(&candidate.pow_header());
                if !pow::meets_target(&digest,candidate.header.target){return Err("GPU network nonce failed CPU reference".into());}
                let current=match get_template(&client,url,&o.user){
                    Ok(t)=>t,
                    Err(e)=>{println!("Local template temporarily unavailable: {e}");next_poll=Instant::now();continue;}
                };
                if current.as_ref().map(|t|(&t.previous_hash,t.current_height))!=Some((&template.previous_hash,template.current_height)) {
                    stale+=1;continue;
                }
                if guard.permits(template.current_height,&template.previous_hash).is_err(){stale+=1;continue;}
                std::fs::create_dir_all("evidence/solo").map_err(|e|e.to_string())?;
                
                
                let pending_path=format!("evidence/solo/pending-{}.json",hex(&digest));
                std::fs::write(&pending_path,serde_json::to_vec(&json!({"height":template.current_height,
                    "block_hash":hex(&digest),"payout_address":o.user,"cpu_verified":true,"block":candidate})).unwrap())
                    .map_err(|e|e.to_string())?;
                let response:Value=match client.post(format!("{url}/api/submit_block")).json(&json!({"block":candidate}))
                    .send().and_then(|r|r.error_for_status()).and_then(|r|r.json()) {
                    Ok(r)=>r,
                    Err(e)=>{emit(&mut file,json!({"event":"submission_unknown","height":template.current_height,
                        "block_hash":hex(&digest),"candidate_file":pending_path,"error":e.to_string()}));
                        println!("Submission outcome unknown; candidate saved: {e}");next_poll=Instant::now();continue;}
                };
                let user_payout=if o.user==DEVELOPER_ADDRESS {split.total} else {split.miner};
                let mut proof=json!({"height":template.current_height,"block_hash":hex(&digest),"nonce":n,
                    "payout_address":o.user,"reward_sats":user_payout,"coinbase_total_sats":split.total,
                    "miner_payout_sats":split.miner,
                    "developer_fee_bps":DEVELOPER_FEE_BPS,"developer_fee_sats":split.developer,
                    "developer_fee_address":DEVELOPER_ADDRESS,
                    "block":candidate,"node_response":response,"cpu_verified":true});
                if response["success"]==true && response["tx_hash"]==hex(&digest) {
                    accepted+=1;println!("ACCEPTED SOLO BLOCK {} | {} | miner {:.8} QBTC | developer fee {:.8} QBTC",
                        template.current_height,hex(&digest),split.miner as f64/1e8,split.developer as f64/1e8);
                    
                    
                    let receipt=relay.post("https://explorer.qbtc-core.org/api/submit_block")
                        .header("Cache-Control","no-cache").json(&json!({"block":candidate}))
                        .send().and_then(|r|r.error_for_status()).and_then(|r|r.json::<Value>());
                    match receipt {
                        Ok(r)=>{
                            let adopted=r["success"]==true && r["tx_hash"]==hex(&digest);
                            println!("PUBLIC NODE RELAY: accepted={adopted} | {r}");
                            proof["public_node_response"]=r;
                            proof["public_node_accepted"]=json!(adopted);
                        },
                        Err(e)=>{println!("PUBLIC NODE RELAY unavailable: {e}; waiting for independent adoption");proof["public_node_relay_error"]=json!(e.to_string());}
                    }
                    std::fs::create_dir_all("evidence/solo").map_err(|e|e.to_string())?;
                    
                    std::fs::write(format!("evidence/solo/block-{}-{}.json",template.current_height,hex(&digest)),serde_json::to_string_pretty(&proof).unwrap()).map_err(|e|e.to_string())?;
                    emit(&mut file,json!({"event":"solo_accepted","proof":proof}));
                    next_poll=Instant::now();
                } else {rejected+=1;println!("SOLO REJECTED: {response}");emit(&mut file,json!({"event":"solo_rejected","proof":proof}));}
                let _=std::fs::remove_file(&pending_path);
                if o.stop_accepted>0 && accepted>=o.stop_accepted {stop.store(true,Ordering::Relaxed);break;}
            }
        } else {std::thread::sleep(Duration::from_millis(50));}
        if last.elapsed()>=Duration::from_secs(5) {
            let rate=(count-last_count) as f64/last.elapsed().as_secs_f64();last=Instant::now();last_count=count;
            println!("SOLO {:.3} GH/s | Accepted blocks {accepted} | Rejected {rejected} | Stale {stale}",rate/1e9);
            emit(&mut file,json!({"event":"stats","hashrate":rate,"hashes":count,"accepted":accepted,"rejected":rejected,"stale":stale,"elapsed_seconds":start.elapsed().as_secs_f64(),"compute_seconds":compute_seconds,"pending":0,"controls":controls.stats(),"gpu_pci":gpu.identity.pci}));
        }
    }
    stop.store(true,Ordering::Relaxed);
    emit(&mut file,json!({"event":"summary","mode":"solo","accepted":accepted,"rejected":rejected,"stale":stale,"hashes":count}));
    if let Some(reason)=guard.safety_stop_reason(){
        emit(&mut file,json!({"event":"fatal","error":reason}));
        return Err(reason);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use bech32::ToBase32;

    fn address_for(byte: u8) -> String {
        bech32::encode("qbtc", [byte; 32].to_base32(), Variant::Bech32m).unwrap()
    }

    fn template(address: &str, reward: u64) -> Template {
        Template {
            previous_hash: "00".repeat(32),
            current_height: 23214,
            target: 123,
            transactions: vec![Transaction {
                inputs: vec![Input { previous_output_hash: [0; 32], vout: 23214 }],
                outputs: vec![Output { value: reward, public_key_hash: payout_hash(address).unwrap(), recovery: None }],
                witnesses: vec![Witness { signature: vec![], public_key: vec![] }],
            }],
        }
    }

    #[test] fn coinbase_cannot_pay_someone_else(){
        let t=template(&address_for(7), 5_000_000_000);
        assert!(assemble(&t,"qbtc10y29nvfuwyxfxhkl4yqkenw4u6hshsk9zgaf5ctz4zfpa2gxe45qtwawce",1).is_err());
    }
    #[test] fn disclosed_fee_splits_full_coinbase_and_conserves_value() {
        let miner_address = address_for(9);
        let reward = 5_000_000_000 + 123_456_789; 
        let (block, split) = assemble(&template(&miner_address, reward), &miner_address, 1).unwrap();
        let outputs = &block.transactions[0].outputs;
        assert_eq!(split.total, reward);
        assert_eq!(split.developer, reward * DEVELOPER_FEE_BPS / 10_000);
        assert_eq!(split.miner + split.developer, split.total);
        assert_eq!(outputs.len(), 2);
        assert_eq!(outputs[0].value, split.miner);
        assert_eq!(outputs[0].public_key_hash, payout_hash(&miner_address).unwrap());
        assert_eq!(outputs[1].value, split.developer);
        assert_eq!(outputs[1].public_key_hash, payout_hash(DEVELOPER_ADDRESS).unwrap());
    }
    #[test] fn same_miner_and_developer_address_keeps_single_full_value_output() {
        let (block, split) = assemble(&template(DEVELOPER_ADDRESS, 5_000_000_000), DEVELOPER_ADDRESS, 1).unwrap();
        assert_eq!(block.transactions[0].outputs.len(), 1);
        assert_eq!(block.transactions[0].outputs[0].value, split.total);
        assert_eq!(split.miner + split.developer, split.total);
    }
    #[test] fn public_pool_endpoint_cannot_be_a_solo_node(){assert!(node_url("http://144.172.110.193:3334").is_err());}
    #[test] fn official_mainnet_coinbase_serialization_and_merkle_roots(){
        
        let tx=Transaction{inputs:vec![Input{previous_output_hash:[0;32],vout:23211}],
            outputs:vec![Output{value:5_000_000_000,public_key_hash:decode32("49dd1a921b58480efd40877ef2fac4813da8397a31df8528d771b83d71ba13e5").unwrap(),recovery:None}],
            witnesses:vec![Witness{signature:vec![],public_key:vec![]}]};
        let txid=Sha256::digest(bincode::serialize(&(&tx.inputs,&tx.outputs)).unwrap());
        let witness=Sha256::digest(bincode::serialize(&tx).unwrap());
        assert_eq!(hex(&txid),"19795b21e81fca26f2aff80c28c88ff761627af15da3524d4fd5f740c40b2f1f");
        assert_eq!(hex(&witness),"e15112df978349363e5fa6120802168a190e7de0871b02df8d529d35adca08b4");
    }
}
