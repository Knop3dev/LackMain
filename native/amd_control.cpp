#define NOMINMAX
#include "SDK/ADLXHelper/Windows/Cpp/ADLXHelper.h"
#include "SDK/Include/IGPUTuning.h"
#include "SDK/Include/IGPUManualGFXTuning.h"
#include "SDK/Include/IGPUManualVRAMTuning.h"
#include "SDK/Include/IGPUManualPowerTuning.h"
#include <windows.h>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <map>
#include <stdexcept>
using namespace adlx;
void check(ADLX_RESULT r){if(ADLX_FAILED(r))throw std::runtime_error("Driver operation failed");}
void* __stdcall allocate(int n){return n>0?std::malloc(n):nullptr;}
void __stdcall release(void** p){if(p){std::free(*p);*p=nullptr;}}
struct Context {
 HMODULE dll=nullptr;void* handle=nullptr;using Destroy=int(__stdcall*)(void*);Destroy destroy=nullptr;
 Context(){
  dll=LoadLibraryW(L"atiadlxx.dll");if(!dll)throw std::runtime_error("AMD ADL unavailable");
  using Create=int(__stdcall*)(void*(__stdcall*)(int),int,void**);
  auto create=(Create)GetProcAddress(dll,"ADL2_Main_Control_Create");destroy=(Destroy)GetProcAddress(dll,"ADL2_Main_Control_Destroy");
  if(!create||!destroy||create(allocate,1,&handle))throw std::runtime_error("AMD context unavailable");
 }
 ~Context(){if(handle&&destroy)destroy(handle);if(dll)FreeLibrary(dll);}
};
struct Settings {
 IADLXManualGraphicsTuning2Ptr gfx;IADLXManualVRAMTuning2Ptr vram;IADLXManualPowerTuningPtr power;
 int core=0,memory=0,limit=0;bool core_changed=false,memory_changed=false,power_changed=false;
 bool restore(){
  bool ok=true;
  if(core_changed){auto r=gfx->SetGPUMaxFrequency(core);ok&=ADLX_SUCCEEDED(r);if(ADLX_SUCCEEDED(r))core_changed=false;}
  if(memory_changed){auto r=vram->SetMaxVRAMFrequency(memory);ok&=ADLX_SUCCEEDED(r);if(ADLX_SUCCEEDED(r))memory_changed=false;}
  if(power_changed){auto r=power->SetPowerLimit(limit);ok&=ADLX_SUCCEEDED(r);if(ADLX_SUCCEEDED(r))power_changed=false;}
  return ok;
 }
 ~Settings(){restore();}
};
int main(int argc,char** argv){
 try{
  std::map<std::string,int> args;
  for(int i=1;i<argc;i++){
   std::string item(argv[i]);auto eq=item.find('=');if(eq==std::string::npos)return 2;
   auto key=item.substr(0,eq);if(key!="--adl-index"&&key!="--core"&&key!="--memory"&&key!="--power")return 2;
   size_t length=0;int number=std::stoi(item.substr(eq+1),&length);if(length!=item.size()-eq-1)return 2;args[key]=number;
  }
  if(!args.count("--adl-index")||args["--adl-index"]<0)return 2;
  Context context;ADLXHelper helper;check(helper.InitializeWithCallerAdl(context.handle,release));
  IADLXGPUPtr gpu;auto mapping=helper.GetAdlMapping();if(!mapping)return 3;
  check(mapping->GetADLXGPUFromAdlAdapterIndex(args["--adl-index"],&gpu));
  IADLXGPUTuningServicesPtr services;check(helper.GetSystemServices()->GetGPUTuningServices(&services));
  Settings previous;IADLXInterfacePtr gi,mi,pi;ADLX_IntRange gr{},mr{},pr{};
  if(args.count("--core")){
   check(services->GetManualGFXTuning(gpu,&gi));previous.gfx=IADLXManualGraphicsTuning2Ptr(gi);if(!previous.gfx)return 3;
   check(previous.gfx->GetGPUMaxFrequency(&previous.core));check(previous.gfx->GetGPUMaxFrequencyRange(&gr));
   if(args["--core"]<gr.minValue||args["--core"]>gr.maxValue)return 2;
  }
  if(args.count("--memory")){
   check(services->GetManualVRAMTuning(gpu,&mi));previous.vram=IADLXManualVRAMTuning2Ptr(mi);if(!previous.vram)return 3;
   check(previous.vram->GetMaxVRAMFrequency(&previous.memory));check(previous.vram->GetMaxVRAMFrequencyRange(&mr));
   if(args["--memory"]<mr.minValue||args["--memory"]>mr.maxValue)return 2;
  }
  if(args.count("--power")){
   check(services->GetManualPowerTuning(gpu,&pi));previous.power=IADLXManualPowerTuningPtr(pi);if(!previous.power)return 3;
   check(previous.power->GetPowerLimit(&previous.limit));check(previous.power->GetPowerLimitRange(&pr));
   if(args["--power"]<pr.minValue||args["--power"]>pr.maxValue)return 2;
  }
  if(args.count("--power")){previous.power_changed=true;check(previous.power->SetPowerLimit(args["--power"]));}
  if(args.count("--memory")){previous.memory_changed=true;check(previous.vram->SetMaxVRAMFrequency(args["--memory"]));}
  if(args.count("--core")){previous.core_changed=true;check(previous.gfx->SetGPUMaxFrequency(args["--core"]));}
  std::puts("{\"applied\":true}");std::fflush(stdout);char buffer[32];std::fgets(buffer,sizeof(buffer),stdin);
  return previous.restore()?0:4;
 }catch(...){std::fputs("AMD tuning failed\n",stderr);return 1;}
}
