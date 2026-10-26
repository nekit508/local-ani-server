import {anime} from "@/api/api";
import APIFail from "@/components/APIFail";
import AnimeComponent from "@/app/anime/AnimeComponent";

export default async function ({ searchParams } : { searchParams: Promise<{ [key:string] : string | string[] | undefined}>}) {
    const params = await searchParams
    const title = params.title as string
    const source = params.source as string

    const animeInfo = await anime(source, title)

    return animeInfo.ok ? (
        <div className="flex flex-col justify-start items-center">
            <AnimeComponent anime={animeInfo.data()} extractor={source}/>
        </div>
    ) : <APIFail message={animeInfo.error_str()}/>
}