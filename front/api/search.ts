import {get} from "@/api/core";

export type ProtoAnime = {
    id: number
    title: string
    thumbnail_url: string
};

export type Extractor = {
    name: string
}

export type EpisodeSource = {
    loaded: boolean
    id: number
    title: string
}

export type Episode = {
    ordinal: number
    title: string
    sources: EpisodeSource[]
}

export type Anime = {
    description: string
    episodes: Episode[]
} & ProtoAnime

export function extractors() {
    return get("/search/extractors")
        .then(res => res.map(b => b as Extractor[]))
}

export function search(extractor: string, query: string) {
    return get(`/search?extractor=${extractor}&query=${query}`)
        .then(res => res.map(b => b as ProtoAnime[]))
}

export function anime(extractor: string, id: number) {
    return get(`/search/anime?extractor=${extractor}&id=${id}`)
        .then(res => res.map(b => b as Anime))
}