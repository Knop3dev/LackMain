
include!("sha_constants.rs");
fn small0(x:u32)->u32{x.rotate_right(7)^x.rotate_right(18)^(x>>3)}
fn small1(x:u32)->u32{x.rotate_right(17)^x.rotate_right(19)^(x>>10)}
pub fn prepare(base:&[u32;32],high:u32)->[u32;169]{
    let mut job=[0u32;169];job[..32].copy_from_slice(base);job[32]=high;
    let [a,b,c,d,e,f,g,h]:[u32;8]=base[24..32].try_into().unwrap();
    let t=h.wrapping_add(e.rotate_right(6)^e.rotate_right(11)^e.rotate_right(25))
        .wrapping_add((e&f)^(!e&g)).wrapping_add(K[10]).wrapping_add(high);
    let u=(a.rotate_right(2)^a.rotate_right(13)^a.rotate_right(22)).wrapping_add((a&b)^(a&c)^(b&c));
    job[33..41].copy_from_slice(&[t.wrapping_add(u),a,b,c,d.wrapping_add(t),e,f,g]);
    let mut words=[None;64];
    for i in 0..16{words[i]=Some(base[8+i]);}
    words[10]=Some(high);words[11]=None;
    for i in 16..64{
        let terms=[words[i-16],words[i-15].map(small0),words[i-7],words[i-2].map(small1)];
        let sum=terms.iter().flatten().fold(0u32,|a,&v|a.wrapping_add(v));
        job[41+i]=sum;
        if terms.iter().all(Option::is_some){words[i]=Some(sum);}
    }
    for i in 0..64{job[105+i]=K[i].wrapping_add(words[i].unwrap_or(0));}
    job
}
