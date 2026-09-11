export function Skeleton({className=''}:{className?:string}){
  return <div className={`animate-pulse rounded-lg bg-border/70 ${className}`}/>
}
export function PageSkeleton(){return <div className="space-y-5"><Skeleton className="h-8 w-56"/><Skeleton className="h-4 w-96 max-w-full"/><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({length:4}).map((_,i)=><Skeleton key={i} className="h-28"/>)}</div><Skeleton className="h-72"/></div>}
