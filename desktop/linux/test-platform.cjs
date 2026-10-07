const {test}=require('node:test');const assert=require('node:assert/strict');
const {requireSupportedGlibc}=require('./platform.cjs');
test('older or absent glibc gives an actionable startup error',()=>{
 for(const version of ['2.35','2.38',undefined,'musl','2.bad'])assert.throws(()=>requireSupportedGlibc(version),/requires glibc 2.39/);
});
test('current and newer glibc can start',()=>{
 for(const version of ['2.39','2.41','3.0'])assert.doesNotThrow(()=>requireSupportedGlibc(version));
});
