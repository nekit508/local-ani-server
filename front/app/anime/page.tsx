import APIFail from "@/components/APIFail";
import AnimeComponent from "@/app/anime/AnimeComponent";
import {anime} from "@/api/search";

export default async function ({ searchParams } : { searchParams: Promise<{ // noinspection JSUnusedLocalSymbols
        [key:string] : string | string[] | undefined}>}) {
    const params = await searchParams
    const title = Number.parseInt(params.title as string)
    const extractor = params.extractor as string

    const ani = await anime(extractor, title)

    return ani.ok ? (
        <div className="flex flex-col justify-start items-center">
            <AnimeComponent anime={ani.data()} extractor={extractor}/>
        </div>
    ) : <APIFail message={ani.error_str()}/>
}