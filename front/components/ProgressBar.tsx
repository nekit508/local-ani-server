export default function ProgressBar({
    progress,
    outerStyle = "",
    innerStyle = "",
    textStyle = "",
}: {
    progress: number;
    outerStyle?: string;
    innerStyle?: string;
    textStyle?: string;
}) {
    const percent = Math.min(100, Math.max(0, progress * 100));

    return (
        <div className={`relative overflow-hidden rounded-full ${outerStyle}`} >
            <div
                className={`absolute top-0 bottom-0 left-0 rounded-full bg-green-600 ${innerStyle}`}
                style={{ width: `${percent}%` }}
            />
            <span className={`absolute inset-0 flex items-center justify-center text-xs ${textStyle}`}>
                {percent.toFixed(0)}%
            </span>
        </div>
    );
}