using System;
using System.IO;
using System.Diagnostics;
using System.Collections.Generic;
using System.Text;

class ChromeMobileLauncher
{
    static int Main(string[] args)
    {
        string logPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "launcher_log.txt");
        try
        {
            File.AppendAllText(logPath, string.Format("\n[{0}] LAUNCH TRIGGERED. Args count: {1}\n", DateTime.Now, args.Length));
            for (int i = 0; i < args.Length; i++)
            {
                File.AppendAllText(logPath, string.Format("  arg[{0}] = {1}\n", i, args[i]));
            }
        }
        catch { }

        string realChrome = FindRealChrome();
        if (string.IsNullOrEmpty(realChrome))
        {
            Console.Error.WriteLine("Error: Google Chrome not found!");
            try { File.AppendAllText(logPath, "ERROR: Chrome not found\n"); } catch { }
            return 1;
        }

        int winWidth = 430;
        int winHeight = 920;
        int winX = 550;
        int winY = 50;
        string userAgent = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36";

        string configPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "mobile_config.txt");
        if (File.Exists(configPath))
        {
            try
            {
                var lines = File.ReadAllLines(configPath);
                foreach (var line in lines)
                {
                    var parts = line.Split(new[] { '=' }, 2);
                    if (parts.Length == 2)
                    {
                        string k = parts[0].Trim().ToLower();
                        string v = parts[1].Trim();
                        if (k == "width") int.TryParse(v, out winWidth);
                        if (k == "height") int.TryParse(v, out winHeight);
                        if (k == "x") int.TryParse(v, out winX);
                        if (k == "y") int.TryParse(v, out winY);
                        if (k == "useragent") userAgent = v;
                    }
                }
            }
            catch { }
        }

        var newArgs = new List<string>();
        string targetUrl = null;

        foreach (var rawArg in args)
        {
            string a = rawArg.Trim();
            if (a.StartsWith("http://", StringComparison.OrdinalIgnoreCase) ||
                a.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            {
                targetUrl = a;
            }
            else
            {
                newArgs.Add(a);
            }
        }

        if (!string.IsNullOrEmpty(targetUrl))
        {
            newArgs.Add("--app=" + targetUrl);
        }

        newArgs.Add(string.Format("--window-size={0},{1}", winWidth, winHeight));
        newArgs.Add(string.Format("--window-position={0},{1}", winX, winY));
        newArgs.Add("--touch-events=enabled");
        newArgs.Add("--force-device-scale-factor=1");
        newArgs.Add(string.Format("--user-agent=\"{0}\"", userAgent));

        // Format all args with quotes if they contain spaces
        var sb = new StringBuilder();
        foreach (var a in newArgs)
        {
            if (sb.Length > 0) sb.Append(" ");

            // If argument contains space and isn't already quoted
            if (a.Contains(" ") && !a.StartsWith("\"") && !a.EndsWith("\""))
            {
                if (a.StartsWith("--user-data-dir=", StringComparison.OrdinalIgnoreCase))
                {
                    string dirVal = a.Substring("--user-data-dir=".Length);
                    sb.Append(string.Format("--user-data-dir=\"{0}\"", dirVal.Trim('\"')));
                }
                else
                {
                    sb.Append(string.Format("\"{0}\"", a));
                }
            }
            else
            {
                sb.Append(a);
            }
        }

        try
        {
            File.AppendAllText(logPath, string.Format("Final command: \"{0}\" {1}\n", realChrome, sb.ToString()));
        }
        catch { }

        var psi = new ProcessStartInfo();
        psi.FileName = realChrome;
        psi.Arguments = sb.ToString();
        psi.UseShellExecute = false;

        try
        {
            var proc = Process.Start(psi);
            if (proc != null)
            {
                proc.WaitForExit();
                try { File.AppendAllText(logPath, string.Format("Exit code: {0}\n", proc.ExitCode)); } catch { }
                return proc.ExitCode;
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("Error launching Chrome: " + ex.Message);
            try { File.AppendAllText(logPath, string.Format("Exception: {0}\n", ex.Message)); } catch { }
            return 1;
        }

        return 0;
    }

    static string FindRealChrome()
    {
        string[] candidates = {
            @"C:\Program Files\Google\Chrome\Application\chrome.exe",
            @"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) + @"\Google\Chrome\Application\chrome.exe"
        };

        foreach (var path in candidates)
        {
            if (File.Exists(path)) return path;
        }
        return null;
    }
}
