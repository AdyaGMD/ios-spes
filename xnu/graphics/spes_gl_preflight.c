/* Run inside the EAGL bridge before replacing any Apple methods.
 * A failed hardware render leaves those methods untouched. No persistent pass flag.
 */
#include <GL/osmesa.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/sysctl.h>
#include <IOKit/IOKitLib.h>
static GLuint spes_shader(GLenum kind,const char *text) {
 GLuint shader=glCreateShader(kind);GLint ok=0;
 glShaderSource(shader,1,&text,NULL);glCompileShader(shader);
 glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
 if(!ok){glDeleteShader(shader);return 0;}return shader;
}
int spes_gl_preflight(void) {
 char args[2048]={0};size_t len=sizeof(args)-1;int enabled=0;
 if(sysctlbyname("kern.bootargs",args,&len,NULL,0)==0){
  args[sizeof(args)-1]=0;
  char *save=NULL;
  for(char *word=strtok_r(args," ",&save);word;word=strtok_r(NULL," ",&save))
   if(!strcmp(word,"spesgpu=1"))enabled=1;
 }
 if(!enabled)return 0; /* The established software boot remains immediately usable. */
 io_service_t service=0;
 for(unsigned i=0;i<300;++i){
  service=IOServiceGetMatchingService(MACH_PORT_NULL,IOServiceMatching("RedwoodGPU"));
  if(service)break;usleep(100000);
 }
 if(!service){fprintf(stderr,"SPES GL: no GPU service; keeping Apple methods\n");return 0;}
 IOObjectRelease(service);
 /* Initial integration uses hardware sysmem rendering, avoiding unverified UBWC. */
 setenv("FD_MESA_DEBUG","sysmem,noubwc",1);
 const int attrs[]={OSMESA_FORMAT,OSMESA_RGBA,OSMESA_PROFILE,OSMESA_ES_PROFILE,
     OSMESA_CONTEXT_MAJOR_VERSION,3,OSMESA_CONTEXT_MINOR_VERSION,0,0};
 OSMesaContext context=OSMesaCreateContextAttribs(attrs,NULL);
 unsigned char pixels[64*64*4];memset(pixels,0,sizeof(pixels));
 if(!context || !OSMesaMakeCurrent(context,pixels,GL_UNSIGNED_BYTE,64,64)){
  if(context)OSMesaDestroyContext(context);return 0;
 }
 const char *renderer=(const char *)glGetString(GL_RENDERER);
 int hardware=renderer && (strstr(renderer,"FD610") || strstr(renderer,"Adreno (TM) 610"));
 fprintf(stderr,"SPES GL: renderer=%s\n",renderer?renderer:"(none)");
 GLuint vs=0,fs=0,program=0;int pass=0;
 if(!hardware)goto done;
 vs=spes_shader(GL_VERTEX_SHADER,"#version 300 es\n in vec2 p; void main(){gl_Position=vec4(p,0,1);}");
 fs=spes_shader(GL_FRAGMENT_SHADER,"#version 300 es\n precision highp float; out vec4 c; void main(){c=vec4(0,1,0,1);}");
 if(!vs || !fs)goto done;
 program=glCreateProgram();glAttachShader(program,vs);glAttachShader(program,fs);
 glBindAttribLocation(program,0,"p");glLinkProgram(program);
 GLint linked=0;glGetProgramiv(program,GL_LINK_STATUS,&linked);if(!linked)goto done;
 glUseProgram(program);glViewport(0,0,64,64);glClearColor(0,0,1,1);glClear(GL_COLOR_BUFFER_BIT);
 const GLfloat triangle[]={-0.75f,-0.75f,0.75f,-0.75f,0.0f,0.75f};
 GLuint vbo=0;glGenBuffers(1,&vbo);glBindBuffer(GL_ARRAY_BUFFER,vbo);
 glBufferData(GL_ARRAY_BUFFER,sizeof(triangle),triangle,GL_STATIC_DRAW);
 glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,0,NULL);glEnableVertexAttribArray(0);
 glDrawArrays(GL_TRIANGLES,0,3);glFinish();
 unsigned char center[4]={0},corner[4]={0};
 glReadPixels(32,32,1,1,GL_RGBA,GL_UNSIGNED_BYTE,center);
 glReadPixels(1,62,1,1,GL_RGBA,GL_UNSIGNED_BYTE,corner);
 pass=glGetError()==GL_NO_ERROR && center[0]<8 && center[1]>247 && center[2]<8 &&
     corner[0]<8 && corner[1]<8 && corner[2]>247;
 glDeleteBuffers(1,&vbo);
 fprintf(stderr,"SPES GL: SHADER %s center=%u,%u,%u corner=%u,%u,%u\n",
     pass?"PASS":"FAIL",center[0],center[1],center[2],corner[0],corner[1],corner[2]);
done:
 if(program)glDeleteProgram(program);if(vs)glDeleteShader(vs);if(fs)glDeleteShader(fs);
 OSMesaDestroyContext(context);
 return pass;
}
