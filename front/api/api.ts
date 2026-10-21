import {get} from "@/api/core";

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