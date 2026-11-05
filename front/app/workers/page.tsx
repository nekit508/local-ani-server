import WorkersInfo from "@/app/workers/WorkersInfo";
import DownloadTasksInfo from "@/app/workers/DownloadTasksInfo";

export default function () {
    return (
        <div className="flex flex-col justify-start items-center">
            <WorkersInfo/>
            <div className="w-full border-b border-foreground/15">

            </div>
            <DownloadTasksInfo/>
        </div>
    )
}