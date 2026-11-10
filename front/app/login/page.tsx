import LoginComponent from "@/app/login/LoginComponent";

export default async function ({ searchParams }: { searchParams: { from?: string } }) {
    searchParams = await searchParams
    return (
        <div className="flex flex-col justify-center items-center size-full">
            <LoginComponent target={ searchParams.from || "home" }/> {/*TODO FIXME vulnerability open redirect*/}
        </div>
    )
}