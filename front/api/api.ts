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

export type State = {
    _type: string
    id: number
    rev: number
    soft_deleted: boolean
}

export type TaskState = State & {
    worker: number,
    error: string
}

export type DownloadTaskState = TaskState & {
    state: string
    quality: number
    title: string
    source_title: string
    ordinal: number
    progress: number
}

export type WorkerState = State & {
    current_task_id: number
    current_task?: TaskState
    error: string
    bad_error: string
    working: boolean
}

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

export function bucket<T extends State>(name: string, since: number = 0) {
    return get(`/api/bucket?name=${name}&since=${since}`).then(res => res.map(b => b as T[]))
}

export function workerRestart(id: number) {
    return get(`/api/worker/restart?id=${id}`).then(res => res.noResponse())
}
