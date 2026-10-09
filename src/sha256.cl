

__constant uint K[64] = {
0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
#define R(x,n) rotate((uint2)(x),(uint2)(32-(n)))
#define S0(x) (R(x,2)^R(x,13)^R(x,22))
#define S1(x) (R(x,6)^R(x,11)^R(x,25))
#define s0(x) (R(x,7)^R(x,18)^((x)>>3))
#define s1(x) (R(x,17)^R(x,19)^((x)>>10))
#ifndef UNROLL
#define UNROLL 1
#endif

inline void hash_nonce(__constant uint *job, ulong base, uint2 st[8]) {
    uint2 w0=job[8];uint2 w1=job[9];uint2 w2=job[10];uint2 w3=job[11];uint2 w4=job[12];uint2 w5=job[13];uint2 w6=job[14];uint2 w7=job[15];uint2 w8=job[16];uint2 w9=job[17];uint2 w10=job[18];uint2 w11=job[19];uint2 w12=job[20];uint2 w13=job[21];uint2 w14=job[22];uint2 w15=job[23];
ulong n0=base+0UL;
ulong n1=base+1UL;
w10=(uint2)((uint)(n0>>32),(uint)(n1>>32));
w11=(uint2)((uint)n0,(uint)n1);
uint2 a=job[24];uint2 b=job[25];uint2 c=job[26];uint2 d=job[27];uint2 e=job[28];uint2 f=job[29];uint2 g=job[30];uint2 h=job[31];
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x243185beU+w10; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x550c7dc3U+w11; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x72be5d74U+w12; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x80deb1feU+w13; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x9bdc06a7U+w14; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xc19bf174U+w15; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w0 += s0(w1)+w9+s1(w14);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xe49b69c1U+w0; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w1 += s0(w2)+w10+s1(w15);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xefbe4786U+w1; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w2 += s0(w3)+w11+s1(w0);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x0fc19dc6U+w2; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w3 += s0(w4)+w12+s1(w1);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x240ca1ccU+w3; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w4 += s0(w5)+w13+s1(w2);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x2de92c6fU+w4; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w5 += s0(w6)+w14+s1(w3);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x4a7484aaU+w5; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w6 += s0(w7)+w15+s1(w4);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x5cb0a9dcU+w6; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w7 += s0(w8)+w0+s1(w5);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x76f988daU+w7; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w8 += s0(w9)+w1+s1(w6);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x983e5152U+w8; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w9 += s0(w10)+w2+s1(w7);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xa831c66dU+w9; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w10 += s0(w11)+w3+s1(w8);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xb00327c8U+w10; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w11 += s0(w12)+w4+s1(w9);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xbf597fc7U+w11; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w12 += s0(w13)+w5+s1(w10);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xc6e00bf3U+w12; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w13 += s0(w14)+w6+s1(w11);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xd5a79147U+w13; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w14 += s0(w15)+w7+s1(w12);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x06ca6351U+w14; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w15 += s0(w0)+w8+s1(w13);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x14292967U+w15; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w0 += s0(w1)+w9+s1(w14);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x27b70a85U+w0; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w1 += s0(w2)+w10+s1(w15);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x2e1b2138U+w1; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w2 += s0(w3)+w11+s1(w0);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x4d2c6dfcU+w2; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w3 += s0(w4)+w12+s1(w1);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x53380d13U+w3; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w4 += s0(w5)+w13+s1(w2);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x650a7354U+w4; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w5 += s0(w6)+w14+s1(w3);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x766a0abbU+w5; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w6 += s0(w7)+w15+s1(w4);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x81c2c92eU+w6; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w7 += s0(w8)+w0+s1(w5);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x92722c85U+w7; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w8 += s0(w9)+w1+s1(w6);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xa2bfe8a1U+w8; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w9 += s0(w10)+w2+s1(w7);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xa81a664bU+w9; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w10 += s0(w11)+w3+s1(w8);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xc24b8b70U+w10; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w11 += s0(w12)+w4+s1(w9);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xc76c51a3U+w11; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w12 += s0(w13)+w5+s1(w10);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xd192e819U+w12; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w13 += s0(w14)+w6+s1(w11);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xd6990624U+w13; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w14 += s0(w15)+w7+s1(w12);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xf40e3585U+w14; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w15 += s0(w0)+w8+s1(w13);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x106aa070U+w15; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w0 += s0(w1)+w9+s1(w14);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x19a4c116U+w0; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w1 += s0(w2)+w10+s1(w15);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x1e376c08U+w1; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w2 += s0(w3)+w11+s1(w0);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x2748774cU+w2; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w3 += s0(w4)+w12+s1(w1);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x34b0bcb5U+w3; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w4 += s0(w5)+w13+s1(w2);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x391c0cb3U+w4; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w5 += s0(w6)+w14+s1(w3);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x4ed8aa4aU+w5; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w6 += s0(w7)+w15+s1(w4);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x5b9cca4fU+w6; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w7 += s0(w8)+w0+s1(w5);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x682e6ff3U+w7; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w8 += s0(w9)+w1+s1(w6);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x748f82eeU+w8; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w9 += s0(w10)+w2+s1(w7);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x78a5636fU+w9; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w10 += s0(w11)+w3+s1(w8);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x84c87814U+w10; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w11 += s0(w12)+w4+s1(w9);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x8cc70208U+w11; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w12 += s0(w13)+w5+s1(w10);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x90befffaU+w12; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w13 += s0(w14)+w6+s1(w11);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xa4506cebU+w13; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w14 += s0(w15)+w7+s1(w12);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xbef9a3f7U+w14; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
w15 += s0(w0)+w8+s1(w13);
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xc67178f2U+w15; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
st[0]=job[0]+a;st[1]=job[1]+b;st[2]=job[2]+c;st[3]=job[3]+d;st[4]=job[4]+e;st[5]=job[5]+f;st[6]=job[6]+g;st[7]=job[7]+h;
a=st[0];b=st[1];c=st[2];d=st[3];e=st[4];f=st[5];g=st[6];h=st[7];
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x428a2f98U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x71374491U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xb5c0fbcfU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xe9b5dba5U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x3956c25bU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x59f111f1U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x923f82a4U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xab1c5ed5U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xd807aa98U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x12835b01U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x243185beU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x550c7dc3U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x72be5d74U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x80deb1feU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x9bdc06a7U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xc19bf534U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xe49b69c1U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xf1564786U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x0fc19dc6U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x240d08cbU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x2de92c6fU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x8a14e4c3U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x5cb0ad9cU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xb2f9d916U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x9b6e5152U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xca486001U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xb0045cc5U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x5f4990b6U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xc3618c59U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xdff55509U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xb3bb35bcU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x70f50446U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xbd517451U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xc5d7cd3fU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x4ed709e1U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x1360ca7aU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xbb738487U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x2d1a4ffcU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xf5300931U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x8e9288f8U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xd02d97b7U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xa8a38a3dU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xadd20c04U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x25bd620eU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x0ad4583fU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xf4e06b64U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x76d02c13U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x0a9f2423U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xac577950U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xdfdaee40U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x8b5f9219U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x07b31fe5U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xa0dda403U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x5ea147edU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xb1fb11c0U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x969a7ec1U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xfbd080ccU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xf87dd418U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x3e32f708U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xa08b3282U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0xa4f804bdU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x282af1beU; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x6b829829U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
{ uint2 t=h+S1(e)+bitselect(g,f,e)+0x2437d895U; uint2 u=S0(a)+bitselect(a,b,a^c); h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u; }
st[0]=st[0]+a;st[1]=st[1]+b;st[2]=st[2]+c;st[3]=st[3]+d;st[4]=st[4]+e;st[5]=st[5]+f;st[6]=st[6]+g;st[7]=st[7]+h;
}
__kernel void search(__constant uint *job, ulong base, ulong target, __global uint *count, __global ulong *nonces, uint capacity) {
ulong nonce=base+(ulong)get_global_id(0)*2UL; uint2 st[8];hash_nonce(job,nonce,st);
if((((ulong)st[0].s0<<32)|st[1].s0)<=target){uint ix=atomic_inc(count);if(ix<capacity)nonces[ix]=nonce+0UL;}
if((((ulong)st[0].s1<<32)|st[1].s1)<=target){uint ix=atomic_inc(count);if(ix<capacity)nonces[ix]=nonce+1UL;}
}
__kernel void digest_test(__constant uint *job, ulong base, __global uint *out) {
uint2 st[8];hash_nonce(job,base+(ulong)get_global_id(0)*2UL,st);
out[(get_global_id(0)*2+0)*8+0]=st[0].s0;
out[(get_global_id(0)*2+0)*8+1]=st[1].s0;
out[(get_global_id(0)*2+0)*8+2]=st[2].s0;
out[(get_global_id(0)*2+0)*8+3]=st[3].s0;
out[(get_global_id(0)*2+0)*8+4]=st[4].s0;
out[(get_global_id(0)*2+0)*8+5]=st[5].s0;
out[(get_global_id(0)*2+0)*8+6]=st[6].s0;
out[(get_global_id(0)*2+0)*8+7]=st[7].s0;
out[(get_global_id(0)*2+1)*8+0]=st[0].s1;
out[(get_global_id(0)*2+1)*8+1]=st[1].s1;
out[(get_global_id(0)*2+1)*8+2]=st[2].s1;
out[(get_global_id(0)*2+1)*8+3]=st[3].s1;
out[(get_global_id(0)*2+1)*8+4]=st[4].s1;
out[(get_global_id(0)*2+1)*8+5]=st[5].s1;
out[(get_global_id(0)*2+1)*8+6]=st[6].s1;
out[(get_global_id(0)*2+1)*8+7]=st[7].s1;
}
