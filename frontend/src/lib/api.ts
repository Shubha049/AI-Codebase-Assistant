export type Repository = {
  id:string; name:string; source_type:string; original_filename:string|null; status:string; error_message:string|null;
  file_count:number; total_size_bytes:number; language_breakdown:Record<string,number>; skipped_file_count:number;
  frameworks:string[]; build_systems:string[]; symbol_count:number; parsed_file_count:number; dependency_edge_count:number;
  chunk_count:number; duplicate_chunk_count:number; chunked_file_count:number; vector_count:number;
  embedding_provider:string|null; embedding_model:string|null; embedding_dimension:number|null; indexed_at:string|null;
  created_at:string; updated_at:string;
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/,'')

function token(){return localStorage.getItem('accessToken')}

type AuthListener = (token: string | null) => void
const authListeners = new Set<AuthListener>()

export function onAuthChange(listener: AuthListener) {
  authListeners.add(listener)
  return () => { authListeners.delete(listener) }
}

function notifyAuth(t: string | null) {
  authListeners.forEach((fn) => {
    try { fn(t) } catch {}
  })
}

async function request<T>(path:string, init?:RequestInit):Promise<T>{
  const headers=new Headers(init?.headers); const t=token(); if(t) headers.set('Authorization',`Bearer ${t}`)
  const res = await fetch(`${API_BASE}${path}`, {...init,headers})
  if(!res.ok){
    if (res.status === 401 && !path.startsWith('/api/v1/auth/login') && !path.startsWith('/api/v1/auth/register')) {
      localStorage.removeItem('accessToken')
      notifyAuth(null)
    }
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') {
        message = body.detail;
      } else if (Array.isArray(body?.detail)) {
        message = body.detail.map((e: any) => e.msg || e.message || JSON.stringify(e)).join('; ');
      } else if (body?.message) {
        message = body.message;
      }
    } catch {}
    throw new Error(message)
  }
  if(res.status===204) return undefined as T
  return res.json()
}

export const api = {
  setToken:(token:string)=>{
    localStorage.setItem('accessToken',token)
    notifyAuth(token)
  },
  clearToken:()=>{
    localStorage.removeItem('accessToken')
    notifyAuth(null)
  },
  getToken:()=>token(),
  hasToken:()=>Boolean(token()),
  login:(email:string,password:string)=>request<any>('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})}),
  register:(email:string,password:string)=>request<any>('/api/v1/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})}),
  me:()=>request<any>('/api/v1/auth/me'),
  base: API_BASE,
  health:()=>request<{status:string}>('/health'),
  repos:()=>request<{repositories:Repository[];total:number}>('/api/v1/repos'),
  repo:(id:string)=>request<Repository>(`/api/v1/repos/${id}`),
  upload:(file:File)=>{const f=new FormData();f.append('file',file);return request<Repository>('/api/v1/repos/upload',{method:'POST',body:f})},
  deleteRepo:(id:string)=>request<void>(`/api/v1/repos/${id}`,{method:'DELETE'}),
  analysis:(id:string)=>request<any>(`/api/v1/repos/${id}/analysis/summary`),
  symbols:(id:string)=>request<any>(`/api/v1/repos/${id}/analysis/symbols?limit=100`),
  architectureOverview:(id:string)=>request<any>(`/api/v1/repos/${id}/architecture/overview`),
  architectureGraph:(id:string)=>request<any>(`/api/v1/repos/${id}/architecture/graph?max_nodes=160`),
  securitySummary:(id:string)=>request<any>(`/api/v1/repos/${id}/security/summary`),
  securityScan:(id:string)=>request<any>(`/api/v1/repos/${id}/security/scan`,{method:'POST'}),
  docsLatest:(id:string)=>request<any>(`/api/v1/repos/${id}/documentation/latest`),
  docsGenerate:(id:string,use_llm=false)=>request<any>(`/api/v1/repos/${id}/documentation/generate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({use_llm})}),
  interviewLatest:(id:string)=>request<any>(`/api/v1/repos/${id}/interview/latest`),
  interviewGenerate:(id:string,body:any)=>request<any>(`/api/v1/repos/${id}/interview/generate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  embeddings:(id:string)=>request<any>(`/api/v1/repos/${id}/embeddings/status`),
  reindex:(id:string,force=false)=>request<any>(`/api/v1/repos/${id}/embeddings/reindex`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({force})}),
  ask:(body:any)=>request<any>('/api/v1/qa/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),
  streamEvents:(repoId:string,onData:(data:any)=>void,onError?:(err:any)=>void)=>{
    const controller = new AbortController();
    const t = token();
    const headers: Record<string, string> = { Accept: 'text/event-stream' };
    if (t) headers['Authorization'] = `Bearer ${t}`;

    fetch(`${API_BASE}/api/v1/repos/${repoId}/events`, {
      headers,
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok || !response.body) {
          throw new Error(`SSE stream failed (${response.status})`);
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const chunks = buffer.split('\n\n');
          buffer = chunks.pop() || '';

          for (const chunk of chunks) {
            const trimmed = chunk.trim();
            if (trimmed.startsWith('data:')) {
              try {
                const data = JSON.parse(trimmed.slice(5).trim());
                onData(data);
              } catch {}
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          onError?.(err);
        }
      });

    return () => controller.abort();
  },
}

export function apiUrl(path:string){return `${API_BASE}${path}`}
