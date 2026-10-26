"use client"

import Image from "next/image";
import {AnimeInfo} from "@/api/api";
import EpisodesTable from "@/app/anime/EpisodesTable";

export default function ({ anime, extractor } : { anime: AnimeInfo, extractor: string }) {
    return (
        <div className="flex flex-col items-center justify-start h-full gap-4 m-4">
            <div className="flex flex-row items-center justify-center gap-4 w-full border-b border-foreground/15 pb-4">
                <Image src={"https:" + anime.thumbnail} alt={anime.title} width={256} height={256} className="object-cover"/>
                <div className="flex flex-col items-start justify-center gap-6">
                    <span className="text-xl"> { anime.title } </span>
                    <span className="text-xs"> { anime.description } </span>
                </div>
            </div>
            <EpisodesTable anime={anime} extractor={extractor}/>
        </div>
    )
}