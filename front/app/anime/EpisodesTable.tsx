import React, {Dispatch, SetStateAction, useState} from "react";
import {Anime, EpisodeSource} from "@/api/search";
import {download, DownloadVideoRequest} from "@/api/videos";

// noinspection JSUnusedLocalSymbols
function send(source: number, ordinals: number[], setLock: Dispatch<SetStateAction<boolean>>, anime: Anime, extractor: string) {
    setLock(true)

    download({
        extractor: extractor,
        q_policy: "<",
        q_target: 2160,
        targets: ordinals.map<DownloadVideoRequest>(ord => {
            return {
                title: anime.id,
                source: source,
                ordinal: ord
            }
        })
    }).then(() => setLock(false))
}

export default function ({ anime, extractor } : { anime: Anime, extractor: string } ) {
    const sources = new Map<string, EpisodeSource>()

    const [lock, setLock] = useState(false)

    for (let episode of anime.episodes) {
        for (let source of episode.sources) {
            if (!sources.has(source.title))
                sources.set(source.title, source)
        }
    }

    return (
        <div className="grid gap-1 grid-cols-[repeat(var(--cols),minmax(0,1fr))]" style={{ '--cols': sources.size + 1 } as React.CSSProperties}>
            <div className=""></div>
            { sources.keys().map(source => {
                return (
                    <div key={ source } className="">
                        <span> { source } </span>
                    </div>
                )
            }).toArray() }
            { anime.episodes.map(episode => {
                const out = [(
                    <span key={ episode.ordinal } className="text-center"> { episode.ordinal } </span>
                )]
                out.push(...sources.keys().map(key => {
                    const source = sources.get(key)
                    const has = episode.sources.find(s => s.title == key) !== undefined
                    return has ? (
                        <button
                            key={`${episode.ordinal}$$${key}`}
                            className="btn-primary"
                            onClick={e => {
                                e.preventDefault()
                                if (has)
                                    send(source?.id as number, [episode.ordinal], setLock, anime, extractor)
                            }}
                            disabled={lock}
                        >
                            { source?.loaded ? "loaded" : "load" }
                        </button>
                    ) : <div key={`${episode.ordinal}$$${key}`}></div>
                }))
                return out
            }) }
        </div>
    )
}