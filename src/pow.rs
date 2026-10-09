
use sha2::{Digest, Sha256};

pub fn encode_header(timestamp: u64, previous: &[u8; 32], merkle: &[u8; 32],
                     commitment: &[u8; 32], nonce: u64, target: u64) -> [u8; 120] {
    let mut bytes = [0u8; 120];
    bytes[0..8].copy_from_slice(&timestamp.to_be_bytes());
    bytes[8..40].copy_from_slice(previous);
    bytes[40..72].copy_from_slice(merkle);
    bytes[72..104].copy_from_slice(commitment);
    bytes[104..112].copy_from_slice(&nonce.to_be_bytes());
    bytes[112..120].copy_from_slice(&target.to_be_bytes());
    bytes
}

pub fn hash_header(bytes: &[u8; 120]) -> [u8; 32] {
    Sha256::digest(bytes).into()
}

pub fn meets_target(hash: &[u8; 32], target: u64) -> bool {
    u64::from_be_bytes(hash[..8].try_into().unwrap()) <= target
}
