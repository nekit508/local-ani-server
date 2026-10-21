export default function ({ message = "Proxy API error" }: { message: string }) {
    return (
        <span className="text-red-700"> { message } </span>
    )
}