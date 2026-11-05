import {get, post} from "@/api/core";

export type SearchedAnime = {
    title: string
    thumbnail: string
}

export type Source = {
    title: string
    url: string
}

export type Episode = {
    ordinal: number
    title: string
    sources: Source[]
}

export type AnimeInfo = {
    thumbnail: string
    title: string
    description: string
    episodes: Episode[]
}

export type State<Dict> = {
    rev: number
    id: number
    data: Dict
    soft_delete: boolean
}

export type WorkerPhase = {
    "phase_name": "DISABLED" | "STARTING" | "PROCESSING_COMMANDS" | "IDLE" | "WORKING" | "ACTIVE" | "FAILED" | "STOPPED"
    "working": boolean
    "alive": boolean
    "active": boolean
    "error": boolean
}

export type WorkerState = State<{
    phase: WorkerPhase
    pending_stop: boolean
    error: string
}>;

export type DownloadTaskState = State<{
    error: string|undefined
    working: boolean
    speed: string
    progress: number
    output_file: string
    name: string
    output_format: string
}>;

export type TargetQuality = 144 | 240 | 360 | 480 | 720| 1080 | 2160
export type QualityPolicy = "<" | ">"

export type DataSource = string

export function dataSources() {
    return get("/api/data_sources").then(res => res.map(s => s as DataSource[]))
}

export function search(source: string, query: string) {
    return get(`/api/search?query=${query}&source=${source}`).then(res => res.map(b => b as SearchedAnime[]))
}

export function anime(source: string, title: string) {
    return get(`/api/anime?source=${source}&title=${title}`).then(res => res.map(b => b as AnimeInfo))
}

export function download(body: {
    extractor: string,
    ordinals: number[],
    title: string,
    source_title: string,
    q_target: TargetQuality,
    q_policy: QualityPolicy
}) {
    return post("/api/download", body).then(res => res.map(b => b as number[]))
}

export function tasks(since: number = 0) {
    return get(`/api/tasks?&since=${since}`).then(res => res.map(b => b as DownloadTaskState[]))
}

export function workers(since: number = 0) {
    return get(`/api/workers?&since=${since}`).then(res => res.map(b => b as WorkerState[]))
}

export function startWorker(wid: number) {
    return get(`/api/worker/${wid}/start`).then(res => res.noResponse())
}

export function stopWorker(wid: number) {
    return get(`/api/worker/${wid}/stop`).then(res => res.noResponse())
}