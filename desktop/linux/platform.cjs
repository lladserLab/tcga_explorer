function requireSupportedGlibc(version) {
 const parts=typeof version==='string'?version.split('.').map(Number):[];
 if(parts.length<2||!Number.isInteger(parts[0])||!Number.isInteger(parts[1])||parts[0]<2||(parts[0]===2&&parts[1]<39)){
  throw new Error('This Linux build requires glibc 2.39 or later, as in Ubuntu 24.04. Use Ubuntu 24.04 or a newer compatible distribution.');
 }
}
module.exports={requireSupportedGlibc};
