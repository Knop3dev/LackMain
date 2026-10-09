pub struct Ranges {base:u64,batch:u64,lane:u64,lanes:u64,position:u64,end:u64,remaining:u64}
impl Ranges {
    pub fn new(base:u64,batch:usize,lane:usize,lanes:usize)->Self {
        let batch=batch as u64;let lanes=lanes as u64;let lane=lane as u64;
        let blocks=((u128::from(u64::MAX)+1)/u128::from(batch)) as u64;
        let end=blocks/lanes+u64::from(lane<blocks%lanes);
        Self{base,batch,lane,lanes,position:0,end,remaining:end}
    }
    pub fn start_at(&mut self,position:u64){if self.end>0{self.position=position%self.end;}}
    pub fn next(&mut self)->Option<u64>{
        if self.remaining==0{return None;}
        let block=self.position*self.lanes+self.lane;
        let nonce=self.base.wrapping_add(block*self.batch);
        self.position=(self.position+1)%self.end;self.remaining-=1;Some(nonce)
    }
}
#[cfg(test)] mod tests {
    use super::*;
    #[test] fn fifteen_gpu_ranges_are_disjoint_across_wraparound(){
        let mut seen=std::collections::HashSet::new();
        for lane in 0..15 {let mut ranges=Ranges::new(u64::MAX-37,128,lane,15);
            for _ in 0..30 {let start=ranges.next().unwrap();for i in 0..128 {assert!(seen.insert(start.wrapping_add(i)));}}
        }
    }
    #[test] fn single_lane_preserves_contiguous_search(){let mut ranges=Ranges::new(7,256,0,1);assert_eq!(ranges.next(),Some(7));assert_eq!(ranges.next(),Some(263));}
    #[test] fn wrapped_lane_exhausts_without_repeating(){let mut ranges=Ranges::new(0,1usize<<63,0,1);ranges.start_at(1);assert_eq!(ranges.next(),Some(1u64<<63));assert_eq!(ranges.next(),Some(0));assert_eq!(ranges.next(),None);}
}
