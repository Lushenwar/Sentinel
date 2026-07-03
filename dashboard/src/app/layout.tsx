import "./globals.css";

export const metadata = { title: "Sentinel", description: "Incident triage dashboard" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header>SENTINEL</header>
        <main>{children}</main>
      </body>
    </html>
  );
}
