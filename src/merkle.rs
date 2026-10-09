use sha2::{Digest, Sha256};

pub fn build_merkle_root(mut layer: Vec<[u8; 32]>) -> [u8; 32] {
    if layer.is_empty() { return [0; 32]; }
    while layer.len() > 1 {
        layer = layer.chunks(2).map(|pair| {
            let mut bytes = [0u8; 64];
            bytes[..32].copy_from_slice(&pair[0]);
            bytes[32..].copy_from_slice(pair.get(1).unwrap_or(&pair[0]));
            Sha256::digest(bytes).into()
        }).collect();
    }
    layer[0]
}
