import {useEffect, useState} from 'react';

export default function useAnalytics(revision) {
  const [state,setState]=useState({data:null,error:'',busy:true});
  useEffect(()=>{
    const controller=new AbortController();
    let active=true;
    const timeout=setTimeout(()=>controller.abort(),15000);
    setState(old=>({...old,error:'',busy:true}));
    fetch('/api/rotation/analytics',{signal:controller.signal})
      .then(async response=>{
        if(!response.ok)throw Error('The local analytics service is unavailable.');
        const data=await response.json();
        if(!Array.isArray(data.rows))throw Error('The analytics response could not be read.');
        if(active)setState({data,error:'',busy:false});
      })
      .catch(error=>{
        if(active)setState(old=>({...old,busy:false,error:error.name==='AbortError'
          ? 'The analytics request timed out.' : error.message}));
      })
      .finally(()=>clearTimeout(timeout));
    return()=>{active=false;clearTimeout(timeout);controller.abort();};
  },[revision]);
  return state;
}
