import Image from "next/image";
import {AnimeInfo, Episode, Source} from "@/api/api";

export default function ({ anime } : { anime: AnimeInfo }) {
    return (
        <div className="flex flex-col items-center justify-start h-full gap-4 m-4">
            <div className="flex flex-row items-center justify-center gap-4 w-full border-b border-foreground/15 pb-4">
                <Image src={"https:" + anime.thumbnail} alt={anime.title} width={256} height={256} className="object-cover"/>
                <div className="flex flex-col items-start justify-center gap-6">
                    <span className="text-xl"> { anime.title } </span>
                    <span className="text-xs"> { anime.description } </span>
                </div>
            </div>
            <EpisodesTable episodes={anime.episodes}/>
        </div>
    )
}

function EpisodesTable({ episodes } : { episodes: Episode[] } ) {
    const sources = new Map<string, Source>()

    for (let episode of episodes) {
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
            { episodes.map(episode => {
                const out = [(
                    <span key={ episode.ordinal } className="text-center"> { episode.ordinal } </span>
                )]
                out.push(...sources.keys().map(key => {
                    const source = sources.get(key)
                    const has = episode.sources.find(source => source.title == key) !== undefined
                    return (
                        <div key={`${episode.ordinal}$$${key}`} className={`${has ? "bg-green-600" : "bg-red-600"}`}>
                        </div>
                    )
                }))
                return out
            }) }
        </div>
    )
}