stopifnot(as.character(getRversion()) == '4.4.2')
required <- c('survival','survminer','jsonlite','ggplot2','svglite','limma','singscore','GSVA','AUCell','survRM2','coxphf','cmprsk','maxstat')
missing <- required[!vapply(required, requireNamespace, logical(1), quietly=TRUE)]
if(length(missing)) stop('Missing runtime packages: ',paste(missing,collapse=', '))
expected <- c(limma='3.62.2',singscore='1.26.0',GSVA='2.0.7',AUCell='1.28.0',survival='3.8.9')
for(name in names(expected)) stopifnot(as.character(packageVersion(name)) == expected[[name]])
cat(jsonlite::toJSON(list(R=as.character(getRversion()),packages=setNames(lapply(required,function(name)as.character(packageVersion(name))),required)),auto_unbox=TRUE,pretty=TRUE))
