import {get, post, request} from "@/api/core";

export type SearchedAnime = {
    title: string
    thumbnail: string
}

export type Source = {
    title: string
    dub: string
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

export type DataSource = string

export type Progress = {
    phase: string | null
    downloaded: number
    total: number
    percent: number
    speed: number | null
    eta: number | null
    fragments_done: number | null
    fragments_total: number | null
}

export type Task = {
    task_id: number
    data_source: string
    title: string
    anime: string
    dub: string
    episode: number
    quality: number | null
    status: string
    rev: number
    attempts: number
    auto_retry: boolean
    error: string | null
    deleted: boolean
    deleted_reason: string | null
    created_at: string | null
    started_at: string | null
    finished_at: string | null
    progress: Progress | null
}

export type WorkerProgress = {
    task_id: number
    anime: string
    dub: string
    episode: number
    status: string
    phase: string | null
    downloaded: number
    total: number
    percent: number
    speed: number | null
    eta: number | null
    fragments_done: number | null
    fragments_total: number | null
}

export type WorkerState = {
    index: number
    state: string
    task_id: number | null
    rev: number
    progress: WorkerProgress | null
}

export type MatrixTask = {
    task_id: number
    title: string
    status: string
    rev: number
    percent: number
    attempts: number
}

export type MatrixItem = {
    anime: string
    dub: string
    episode: number
    exists: boolean
    ext: string | null
    rev: number
    task: MatrixTask | null
}

export type RemovedItem = {
    anime: string
    dub: string
    episode: number
    rev?: number
}

export type Feed<T> = {
    epoch: string
    rev: number
    updated: T[]
    removed: RemovedItem[]
}

export type WorkersFeed = {
    epoch: string
    rev: number
    updated: WorkerState[]
    removed: []
}

export type TaskStartResult = {
    created: Record<string, number>
    exists: number[]
    active: Record<string, number>
    errors: Record<string, string>
}

export type FileEntry = {
    name: string
    type: "dir" | "file"
    size: number | null
    mtime: number
    path: string
}

export type FilesListing = {
    root: string
    path: string
    parent: string | null
    items: FileEntry[]
}

export function dataSources() {
    return get("/api/data_sources").then(res => res.map(s => s as DataSource[]))
}

export function search(source: string, query: string) {
    return get(`/api/search?query=${encodeURIComponent(query)}&source=${encodeURIComponent(source)}`)
        .then(res => res.map(b => b as SearchedAnime[]))
}

export function anime(source: string, title: string) {
    return get(`/api/anime?source=${encodeURIComponent(source)}&title=${encodeURIComponent(title)}`)
        .then(res => res.map(b => b as AnimeInfo))
}

export function startTasks(data: {
    data_source: string
    title: string
    dub: string
    episodes: number[]
    quality: number | null
}) {
    return post("/api/tasks", data)
        .then(res => res.map(b => b as TaskStartResult))
}

export function tasksFeed(since: number = 0) {
    return get(`/api/tasks?since=${since}`)
        .then(res => res.map(b => b as Feed<Task>))
}

export function workersFeed(since: number = 0) {
    return get(`/api/workers?since=${since}`)
        .then(res => res.map(b => b as WorkersFeed))
}

export function matrixFeed(animeTitle: string, since: number = 0) {
    return get(`/api/matrix?anime=${encodeURIComponent(animeTitle)}&since=${since}`)
        .then(res => res.map(b => b as Feed<MatrixItem>))
}

export function pauseTask(taskId: number) {
    return post(`/api/tasks/${taskId}/pause`, {})
        .then(res => res.map(b => b as { paused: boolean }))
}

export function resumeTask(taskId: number) {
    return post(`/api/tasks/${taskId}/resume`, {})
        .then(res => res.map(b => b as { resumed: boolean }))
}

export function retryTask(taskId: number) {
    return post(`/api/tasks/${taskId}/retry`, {})
        .then(res => res.map(b => b as { retried: boolean }))
}

export function deleteTask(taskId: number) {
    return request(`/api/tasks/${taskId}`, "DELETE", null)
        .then(res => res.map(b => b as { deleted: boolean }))
}

export function listFiles(path: string = "") {
    return get(`/api/files?path=${encodeURIComponent(path)}`)
        .then(res => res.map(b => b as FilesListing))
}

export function deleteFile(path: string) {
    return request(`/api/files?path=${encodeURIComponent(path)}`, "DELETE", null)
        .then(res => res.map(b => b as { removed: boolean, type: string }))
}
