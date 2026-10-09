

#define NOMINMAX
#include "SDK/ADLXHelper/Windows/Cpp/ADLXHelper.h"
#include "SDK/Include/IGPUTuning.h"
#include "SDK/Include/IGPUManualGFXTuning.h"
#include "SDK/Include/IGPUManualPowerTuning.h"
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <algorithm>
#include <windows.h>
#include <string>
#include <cctype>
using namespace adlx;
#define CHECK(expr) {auto r=(expr);if(ADLX_FAILED(r)){std::fprintf(stderr,"%s: %d\n",#expr,(int)r);return 1;}}
struct Restore {
    IADLXManualGraphicsTuning2Ptr& gfx;IADLXManualPowerTuningPtr& power;
    int frequency,limit,voltage;bool clockChanged=false,powerChanged=false,voltageChanged=false;
    int run(){
        int result=0;
        if(voltageChanged){auto r=gfx->SetGPUVoltage(voltage);std::fprintf(stderr,"Restore voltage %d: %d\n",voltage,(int)r);
            if(ADLX_FAILED(r))result=4;else voltageChanged=false;}
        if(clockChanged){auto r=gfx->SetGPUMaxFrequency(frequency);std::fprintf(stderr,"Restore frequency %d: %d\n",frequency,(int)r);
            if(ADLX_FAILED(r))result=4;else clockChanged=false;}
        if(powerChanged){auto r=power->SetPowerLimit(limit);std::fprintf(stderr,"Restore power limit %d: %d\n",limit,(int)r);
            if(ADLX_FAILED(r))result=4;else powerChanged=false;}
        return result;
    }
    ~Restore(){run();}
};
void* __stdcall adlAllocate(int n){return n>0?std::malloc((size_t)n):nullptr;}
void __stdcall adlFree(void** p){if(p){std::free(*p);*p=nullptr;}}
struct ADLContext { HMODULE dll=nullptr;void* context=nullptr;using Destroy=int (__stdcall*)(void*);Destroy destroy=nullptr;
    ~ADLContext(){if(context&&destroy)destroy(context);if(dll)FreeLibrary(dll);}
    bool init(){dll=LoadLibraryW(L"atiadlxx.dll");if(!dll)return false;using Create=int (__stdcall*)(void* (__stdcall*)(int),int,void**);auto create=(Create)GetProcAddress(dll,"ADL2_Main_Control_Create");destroy=(Destroy)GetProcAddress(dll,"ADL2_Main_Control_Destroy");return create&&destroy&&create(adlAllocate,1,&context)==0;}
};
int main(int argc,char** argv){
    int adlIndex=-1;bool requestedChange=false;
    for(int i=1;i<argc;i++){if(std::strncmp(argv[i],"--adl-index=",12)==0){char* end=nullptr;adlIndex=(int)std::strtol(argv[i]+12,&end,10);if(*end||adlIndex<0)return 2;}else requestedChange=true;}
    if(adlIndex<0)return 2;
    ADLContext adl;if(!adl.init()){std::fprintf(stderr,"ADL context unavailable\n");return 1;}
    ADLXHelper helper;CHECK(helper.InitializeWithCallerAdl(adl.context,adlFree));
    IADLXGPUPtr gpu;auto mapping=helper.GetAdlMapping();if(!mapping){std::fprintf(stderr,"ADLX ADL mapping unavailable\n");return 1;}
    CHECK(mapping->GetADLXGPUFromAdlAdapterIndex(adlIndex,&gpu));
    IADLXGPUTuningServicesPtr tuning;CHECK(helper.GetSystemServices()->GetGPUTuningServices(&tuning));
    IADLXInterfacePtr gfxInterface,powerInterface;
    CHECK(tuning->GetManualGFXTuning(gpu,&gfxInterface));
    IADLXManualGraphicsTuning2Ptr gfx(gfxInterface);
    if(!gfx){std::fprintf(stderr,"GraphicsTuning2 unsupported\n");return 1;}
    ADLX_IntRange minRange{},maxRange{},voltageRange{},powerRange{};
    int minFreq=0,maxFreq=0,voltage=0,power=0;
    CHECK(gfx->GetGPUMinFrequencyRange(&minRange));CHECK(gfx->GetGPUMaxFrequencyRange(&maxRange));
    CHECK(gfx->GetGPUVoltageRange(&voltageRange));CHECK(gfx->GetGPUMinFrequency(&minFreq));
    CHECK(gfx->GetGPUMaxFrequency(&maxFreq));CHECK(gfx->GetGPUVoltage(&voltage));
    CHECK(tuning->GetManualPowerTuning(gpu,&powerInterface));
    IADLXManualPowerTuningPtr p(powerInterface);if(!p)return 1;
    CHECK(p->GetPowerLimitRange(&powerRange));CHECK(p->GetPowerLimit(&power));
    std::printf("{\"min_frequency_mhz\":%d,\"max_frequency_mhz\":%d,\"voltage_setting_mv\":%d,\"power_limit_percent\":%d,"
        "\"min_frequency_range\":[%d,%d],\"max_frequency_range\":[%d,%d],\"voltage_range_mv\":[%d,%d],\"power_range_percent\":[%d,%d]}\n",
        minFreq,maxFreq,voltage,power,minRange.minValue,minRange.maxValue,maxRange.minValue,maxRange.maxValue,
        voltageRange.minValue,voltageRange.maxValue,powerRange.minValue,powerRange.maxValue);
    std::fflush(stdout);
    if(requestedChange){
        long requested=power,requestedFrequency=maxFreq,requestedVoltage=voltage;
        for(int i=1;i<argc;i++){
            if(std::strncmp(argv[i],"--adl-index=",12)==0)continue;
            const char* value=nullptr;bool isPower=false,isVoltage=false;
            if(std::strncmp(argv[i],"--power-limit=",14)==0){value=argv[i]+14;isPower=true;}
            else if(std::strncmp(argv[i],"--max-frequency=",16)==0)value=argv[i]+16;
            else if(std::strncmp(argv[i],"--voltage-mv=",13)==0){value=argv[i]+13;isVoltage=true;}
            else return 2;
            char* end=nullptr;long n=std::strtol(value,&end,10);
            if(!end || *end || end==value)return 2;
            if(isPower)requested=n;else if(isVoltage)requestedVoltage=n;else requestedFrequency=n;
        }
        if(requested<powerRange.minValue || requested>power || requestedFrequency<std::max(minFreq,maxRange.minValue) || requestedFrequency>maxFreq || requestedVoltage<voltageRange.minValue || requestedVoltage>voltage){
            std::fprintf(stderr,"Only reductions within driver limits are permitted\n");return 2;}
        Restore restore{gfx,p,maxFreq,power,voltage};
        restore.powerChanged=true;
        CHECK(p->SetPowerLimit((int)requested));
        if(requestedFrequency!=maxFreq){restore.clockChanged=true;CHECK(gfx->SetGPUMaxFrequency((int)requestedFrequency));}
        if(requestedVoltage!=voltage){restore.voltageChanged=true;CHECK(gfx->SetGPUVoltage((int)requestedVoltage));}
        int actual=0,actualFrequency=0,actualVoltage=0;
        auto readResult=p->GetPowerLimit(&actual);
        auto freqResult=gfx->GetGPUMaxFrequency(&actualFrequency);
        auto voltageResult=gfx->GetGPUVoltage(&actualVoltage);
        if(ADLX_FAILED(readResult)||actual!=requested||ADLX_FAILED(freqResult)||actualFrequency!=requestedFrequency||ADLX_FAILED(voltageResult)||actualVoltage!=requestedVoltage)return 3;
        std::printf("{\"applied_power_limit_percent\":%d,\"applied_max_frequency_mhz\":%d,\"applied_voltage_setting_mv\":%d}\n",actual,actualFrequency,actualVoltage);std::fflush(stdout);
        char buffer[64];std::fgets(buffer,sizeof(buffer),stdin);
        return restore.run();
    }
    return 0;
}
