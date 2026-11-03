using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;
using System.Security.Cryptography;
using System.Threading;

internal static class SmartOrderNativeLauncher
{
    private const int UNIVERSAL_NAME_INFO_LEVEL = 1;
    private const int ERROR_MORE_DATA = 234;

    [DllImport("mpr.dll", CharSet = CharSet.Unicode)]
    private static extern int WNetGetUniversalName(string localPath, int infoLevel, IntPtr buffer, ref int bufferSize);

    private static string LocalBase
    {
        get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SmartOrder"); }
    }

    private static void Log(string text)
    {
        try
        {
            string dir = Path.Combine(LocalBase, "logs");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "launcher.log"), DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + " | NATIVE | " + text + Environment.NewLine, Encoding.UTF8);
        }
        catch { }
    }

    private static string ReadText(string path, string fallback)
    {
        try
        {
            string value = File.ReadAllText(path, Encoding.UTF8).Trim();
            return value.Length == 0 ? fallback : value;
        }
        catch { return fallback; }
    }

    private static string ToUnc(string path)
    {
        try
        {
            if (String.IsNullOrEmpty(path) || path.Length < 3 || path[1] != ':') return path;
            int size = 0;
            int result = WNetGetUniversalName(path, UNIVERSAL_NAME_INFO_LEVEL, IntPtr.Zero, ref size);
            if (result != ERROR_MORE_DATA || size <= 0) return path;
            IntPtr buffer = Marshal.AllocHGlobal(size);
            try
            {
                result = WNetGetUniversalName(path, UNIVERSAL_NAME_INFO_LEVEL, buffer, ref size);
                if (result != 0) return path;
                IntPtr namePtr = Marshal.ReadIntPtr(buffer);
                string unc = Marshal.PtrToStringUni(namePtr);
                return String.IsNullOrEmpty(unc) ? path : unc;
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }
        catch { return path; }
    }

    private static void CopyPayload(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        var psi = new ProcessStartInfo
        {
            FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "robocopy.exe"),
            Arguments = "\"" + source + "\" \"" + destination + "\" /MIR /R:1 /W:1 /NFL /NDL /NJH /NJS /NP",
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden
        };
        using (Process p = Process.Start(psi))
        {
            p.WaitForExit();
            if (p.ExitCode > 7) throw new InvalidOperationException("SmartOrder local cache update failed. Robocopy=" + p.ExitCode);
        }
    }

    private static string Digest(string text)
    {
        using (SHA256 hash = SHA256.Create())
            return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(text))).Replace("-", "").ToLowerInvariant();
    }

    private static void VerifyPayload(string folder, string manifest)
    {
        string prefix = Path.GetFullPath(folder).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        int checkedFiles = 0;
        foreach (string line in manifest.Split(new char[] {'\r', '\n'}, StringSplitOptions.RemoveEmptyEntries))
        {
            if (line.Length < 67 || line[64] != ' ' || line[65] != '*')
                throw new InvalidOperationException("Invalid SmartOrder SHA-256 manifest.");
            string relative = line.Substring(66).Replace('/', Path.DirectorySeparatorChar);
            string file = Path.GetFullPath(Path.Combine(folder, relative));
            if (!file.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) || !File.Exists(file))
                throw new InvalidOperationException("SmartOrder payload file is missing: " + relative);
            string actual;
            using (SHA256 hash = SHA256.Create())
            using (FileStream stream = File.OpenRead(file))
                actual = BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
            if (!String.Equals(actual, line.Substring(0, 64), StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("SmartOrder checksum mismatch: " + relative);
            checkedFiles++;
        }
        if (checkedFiles == 0 || !File.Exists(Path.Combine(folder, "SmartOrderApp.exe")) || !Directory.Exists(Path.Combine(folder, "_internal")))
            throw new InvalidOperationException("SmartOrder payload is incomplete.");
    }

    private static void PrepareCache(string source, string destination, string buildId, string manifest)
    {
        string manifestHash = Digest(manifest);
        string marker = Path.Combine(destination, ".verified.sha256");
        using (Mutex gate = new Mutex(false, "Local\\SmartOrderCache_" + Digest(destination).Substring(0, 24)))
        {
            bool acquired = false;
            try
            {
                try { acquired = gate.WaitOne(TimeSpan.FromSeconds(45)); }
                catch (AbandonedMutexException) { acquired = true; }
                if (!acquired) throw new InvalidOperationException("Another SmartOrder launcher is preparing the local cache. Try again shortly.");
                if (File.Exists(Path.Combine(destination, "SmartOrderApp.exe")) &&
                    Directory.Exists(Path.Combine(destination, "_internal")) &&
                    ReadText(Path.Combine(destination, "build.id"), "") == buildId &&
                    ReadText(marker, "") == manifestHash) return;

                string staging = destination + ".staging." + Guid.NewGuid().ToString("N");
                try
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(destination));
                    CopyPayload(source, staging);
                    if (ReadText(Path.Combine(staging, "build.id"), "") != buildId)
                        throw new InvalidOperationException("The server build changed while copying. Please retry after the update finishes.");
                    VerifyPayload(staging, manifest);
                    File.WriteAllText(Path.Combine(staging, ".verified.sha256"), manifestHash, Encoding.ASCII);
                    if (Directory.Exists(destination))
                    {
                        // Preserve an uncertain cache rather than mirroring over loaded DLLs.
                        Directory.Move(destination, destination + ".previous." + Guid.NewGuid().ToString("N"));
                    }
                    Directory.Move(staging, destination);
                }
                finally { if (Directory.Exists(staging)) Directory.Delete(staging, true); }
            }
            finally { if (acquired) gate.ReleaseMutex(); }
        }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        var sw = Stopwatch.StartNew();
        try
        {
            string sourceDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            string localBase = LocalBase;
            Directory.CreateDirectory(localBase);

            // When executed from a mapped drive, preserve a stable UNC database path.
            string networkRoot = ToUnc(Directory.GetParent(sourceDir).FullName);
            string networkSource = ToUnc(sourceDir);

            // If somebody accidentally runs the cached launcher, reuse the saved server root.
            if (sourceDir.StartsWith(localBase, StringComparison.OrdinalIgnoreCase))
            {
                string rootFile = Path.Combine(sourceDir, "network_root.txt");
                if (!File.Exists(rootFile)) rootFile = Path.Combine(localBase, "network_root.txt");
                string saved = ReadText(rootFile, "");
                if (!String.IsNullOrWhiteSpace(saved))
                {
                    networkRoot = saved;
                    networkSource = Path.Combine(networkRoot, "SmartOrderApp");
                }
            }

            string version = ReadText(Path.Combine(networkSource, "version.txt"), "1.0");
            if (version.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 || version.Contains(".."))
                throw new InvalidOperationException("Invalid SmartOrder version file.");
            string buildId = ReadText(Path.Combine(networkSource, "build.id"), version);
            string manifest = File.ReadAllText(Path.Combine(networkSource, "manifest.sha256"), Encoding.UTF8);
            // A distinct share/build has a distinct immutable local directory.
            string shareKey = Digest(networkRoot.TrimEnd('\\').ToLowerInvariant()).Substring(0,16);
            string localDir = Path.Combine(Path.Combine(Path.Combine(Path.Combine(localBase, "App"),shareKey),version),Digest(buildId+"|"+manifest).Substring(0,16));
            string localExe = Path.Combine(localDir, "SmartOrderApp.exe");

            Log("probe=" + sw.ElapsedMilliseconds + "ms | version=" + version + " | network=" + networkRoot);

            PrepareCache(networkSource, localDir, buildId, manifest);
            Log("cache-ready=" + sw.ElapsedMilliseconds + "ms | build=" + buildId);

            File.WriteAllText(Path.Combine(localBase, "network_root.txt"), networkRoot, Encoding.UTF8);

            var start = new ProcessStartInfo
            {
                FileName = localExe,
                WorkingDirectory = localDir,
                UseShellExecute = false
            };
            if (args.Length > 0)
            {
                if (args.Length != 1 || args[0].IndexOf('"') >= 0 ||
                    !args[0].EndsWith(".sorder", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Expected one SmartOrder .sorder file.");
                // Windows file names cannot contain quotes; .sorder has no
                // trailing slash. Preserve spaces, Unicode and UNC paths.
                start.Arguments = "\"" + Path.GetFullPath(args[0]) + "\"";
            }
            start.EnvironmentVariables["SMARTORDER_NETWORK_ROOT"] = networkRoot;
            start.EnvironmentVariables["SMARTORDER_DB_PATH"] = Path.Combine(networkRoot, "work_orders.db");
            Process.Start(start);
            Log("child-started=" + sw.ElapsedMilliseconds + "ms | local=" + localExe);
            return 0;
        }
        catch (Exception ex)
        {
            Log("ERROR | " + ex);
            MessageBox.Show("SmartOrder could not start.\r\n\r\n" + ex.Message, "SmartOrder", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
