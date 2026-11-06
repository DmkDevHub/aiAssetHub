using System;
using System.IO;
using System.Diagnostics;
using System.Runtime.InteropServices;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace AIAssetHub.Editor
{
    // No socket, runtime component, asset scan, inference or scene save.
    [InitializeOnLoad]
    public static class Connector
    {
        [Serializable] public class State
        {
            public int protocol = 1, pid;
            public string session, token, project, editorVersion, scene, sceneHandle, updatedAt;
            public bool playing, compiling, sceneDirty, batchMode;
        }
        [Serializable] public class Request
        {
            public string id, session, token, action, expiresAt;
        }
        [Serializable] public class Result
        {
            public string id, session, token, status, errorCode;
            public State target;
        }
        static readonly string Project = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        static readonly string DirectoryPath = Path.Combine(Project, "Library", "AIAssetHub");
        static readonly string Session = Guid.NewGuid().ToString();
        static readonly string Token = Guid.NewGuid().ToString("N") + Guid.NewGuid().ToString("N");
        static double nextTick;
        static bool reported;
        public static string MailboxPath => DirectoryPath;

        static Connector()
        {
            EditorApplication.update += Tick;
            EditorApplication.quitting += Stop;
            AssemblyReloadEvents.beforeAssemblyReload += Stop;
        }
        public static void NoLinks(string path)
        {
            for (var item = new DirectoryInfo(Path.GetFullPath(path)); item != null; item = item.Parent)
                if ((item.Exists || File.Exists(item.FullName)) && (File.GetAttributes(item.FullName) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("UNSAFE_PATH");
        }
        static void Protect(string path, bool directory)
        {
            if (!OpenProcessToken(GetCurrentProcess(), 8, out var token)) throw new IOException();
            IntPtr buffer = IntPtr.Zero, text = IntPtr.Zero, descriptor = IntPtr.Zero;
            try
            {
                GetTokenInformation(token, 1, IntPtr.Zero, 0, out var size);
                buffer = Marshal.AllocHGlobal((int)size);
                if (!GetTokenInformation(token, 1, buffer, size, out _) ||
                    !ConvertSidToStringSid(Marshal.ReadIntPtr(buffer), out text)) throw new IOException();
                var sid = Marshal.PtrToStringUni(text);
                var sddl = "O:" + sid + "D:P(A;;FA;;;SY)(A;;FA;;;" + sid + ")";
                if (!ConvertStringSecurityDescriptorToSecurityDescriptor(sddl, 1, out descriptor, IntPtr.Zero) ||
                    !SetFileSecurity(path, 0x80000004, descriptor)) throw new IOException();
            }
            finally
            {
                if (buffer != IntPtr.Zero) Marshal.FreeHGlobal(buffer);
                if (text != IntPtr.Zero) LocalFree(text);
                if (descriptor != IntPtr.Zero) LocalFree(descriptor);
                CloseHandle(token);
            }
        }
        [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
        [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr handle);
        [DllImport("advapi32.dll")] static extern bool OpenProcessToken(IntPtr process, uint access, out IntPtr token);
        [DllImport("advapi32.dll")] static extern bool GetTokenInformation(IntPtr token, int kind, IntPtr buffer, uint size, out uint required);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, EntryPoint = "ConvertSidToStringSidW")] static extern bool ConvertSidToStringSid(IntPtr sid, out IntPtr text);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, EntryPoint = "ConvertStringSecurityDescriptorToSecurityDescriptorW")] static extern bool ConvertStringSecurityDescriptorToSecurityDescriptor(string text, uint revision, out IntPtr descriptor, IntPtr size);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, EntryPoint = "SetFileSecurityW")] static extern bool SetFileSecurity(string path, uint flags, IntPtr descriptor);
        public static void WritePrivate(string path, object value)
        {
            NoLinks(path); string temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                using (var stream = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    Protect(temp, false);
                    var bytes = System.Text.Encoding.UTF8.GetBytes(JsonUtility.ToJson(value));
                    stream.Write(bytes, 0, bytes.Length); stream.Flush(true);
                }
                if (File.Exists(path)) File.Replace(temp, path, null); else File.Move(temp, path);
                Protect(path, false);
            }
            finally { if (File.Exists(temp)) File.Delete(temp); }
        }
        public static State CurrentState()
        {
            var scene = SceneManager.GetActiveScene();
            return new State { pid = Process.GetCurrentProcess().Id, session = Session, token = Token,
                project = Project, editorVersion = Application.unityVersion,
                scene = scene.path, sceneHandle = scene.handle.ToString(), sceneDirty = scene.isDirty,
                playing = EditorApplication.isPlayingOrWillChangePlaymode, compiling = EditorApplication.isCompiling,
                batchMode = Application.isBatchMode, updatedAt = DateTime.UtcNow.ToString("o") };
        }
        public static void Tick()
        {
            if (EditorApplication.timeSinceStartup < nextTick) return;
            nextTick = EditorApplication.timeSinceStartup + .1;
            if (Application.platform != RuntimePlatform.WindowsEditor) return;
            try
            {
                NoLinks(DirectoryPath); Directory.CreateDirectory(DirectoryPath); Protect(DirectoryPath, true);
                WritePrivate(Path.Combine(DirectoryPath, "connector.json"), CurrentState());
                var requests = Directory.GetFiles(DirectoryPath, "*.request.json");
                Array.Sort(requests, StringComparer.Ordinal);
                int processed = 0;
                foreach (var path in requests)
                {
                    if (++processed > 20) break;
                    NoLinks(path);
                    if (new FileInfo(path).Length > 16384) continue;
                    var r = JsonUtility.FromJson<Request>(File.ReadAllText(path));
                    if (r == null || !Guid.TryParseExact(r.id, "D", out _) ||
                        Path.GetFileName(path) != r.id + ".request.json" || r.session != Session || r.token != Token) continue;
                    var output = Path.Combine(DirectoryPath, r.id + ".result.json");
                    if (File.Exists(output)) continue; // At most once in this Editor session.
                    var result = new Result { id = r.id, session = Session, token = Token, status = "failed" };
                    if (!DateTime.TryParse(r.expiresAt, null, System.Globalization.DateTimeStyles.RoundtripKind, out var deadline) || deadline.ToUniversalTime() < DateTime.UtcNow)
                        result.errorCode = "UNITY_REQUEST_EXPIRED";
                    else if (r.action == "ping") { result.status = "succeeded"; result.target = CurrentState(); }
                    else result.errorCode = "UNITY_ACTION_NOT_ALLOWED";
                    WritePrivate(output, result);
                }
            }
            catch (Exception error)
            {
                if (!reported) UnityEngine.Debug.LogError("AIAssetHub channel unavailable: " + error.GetType().Name);
                reported = true; // Never log paths, secrets, arguments or raw exception messages.
            }
        }
        static void Stop()
        {
            try { var path = Path.Combine(DirectoryPath, "connector.json"); NoLinks(path); if (File.Exists(path)) File.Delete(path); }
            catch (Exception) { }
        }
    }
}
