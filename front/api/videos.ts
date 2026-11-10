import {post} from "@/api/core";

export type TargetQuality = 144 | 240 | 360 | 480 | 720| 1080 | 2160

export type QualityPolicy = "<" | ">"

export type DownloadVideoRequest = {
    ordinal: number
    title: number
    source: number
}

export type DownloadFailsInfo = {
    "failed_titles": number[]
    "failed_sources": [number, number][]
    "failed_episodes": [number, number, number][]
}

export function download(body: {
    extractor: string,
    q_target: TargetQuality,
    q_policy: QualityPolicy,
    targets: DownloadVideoRequest[]
}) {
    return post("/videos/download", body)
        .then(res => res.map(_ => _ as DownloadFailsInfo))
}