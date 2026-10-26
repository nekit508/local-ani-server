import {AnimeInfo, download, Source} from "@/api/api";
import {Dispatch, SetStateAction, useState} from "react";

function send(source_title: string, ordinals: number[], setLock: Dispatch<SetStateAction<boolean>>, anime: AnimeInfo, extractor: string) {
    setLock(true)
    download({
        extractor: extractor,
        ordinals: ordinals,
        title: anime.title,
        source_title: source_title,
        q_target: 2160,
        q_policy: "<",
    }).then(res => {
        setLock(false)
    })
}

export default function ({ anime, extractor } : { anime: AnimeInfo, extractor: string } ) {
    const sources = new Map<string, Source>()

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
                                if (has) {
                                    console.log(source)
                                    send(source?.title as string, [episode.ordinal], setLock, anime, extractor)
                                }
                            }}
                            disabled={lock}
                        >
                        </button>
                    ) : <div key={`${episode.ordinal}$$${key}`}></div>
                }))
                return out
            }) }
        </div>
    )
}