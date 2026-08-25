import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { I18nProvider } from "@/lib/i18n/provider";

export const metadata: Metadata = {
  title: "WaterExpert · 水环境智能分析平台",
  description:
    "WaterExpert 水环境智能分析工作台：浊度/清澈度预测与验证、致浑因子诊断、响应与预案、边界变化识别、Sobol 敏感性分析与知识图谱问答。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className="antialiased bg-background text-foreground">
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem
          disableTransitionOnChange
        >
          <I18nProvider>{children}</I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
