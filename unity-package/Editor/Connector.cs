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
            public int sceneRevision;
            public bool playing, compiling, sceneDirty, batchMode, prefabStage;
        }
        [Serializable] public class Request
        {
            public string id, session, token, action, expiresAt;
            public Item[] items;
            public string scene, sceneHandle, name;
            public int sceneRevision;
            public float[] position, rotation, scale;
        }
        [Serializable] public class Item
        {
            public string assetId, fileId, sourcePath, targetRelativePath, mtimeNs, sha256, guid;
            public long size;
        }
        [Serializable] public class ItemResult
        {
            public string assetId, fileId, status, errorCode, assetPath, guid;
            public bool copied;
            public string objectId, objectName, scene, sceneHandle;
            public string entityId;
            public float[] position, rotation, scale;
            public bool sceneDirty, sceneSaved;
        }
        [Serializable] public class Result
        {
            public string id, session, token, status, errorCode;
            public State target;
            public ItemResult[] items;
        }
        static readonly string Project = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        static readonly string DirectoryPath = Path.Combine(Project, "Library", "AIAssetHub");
        static readonly string Session = Guid.NewGuid().ToString();
        static readonly string Token = Guid.NewGuid().ToString("N") + Guid.NewGuid().ToString("N");
        static double nextTick;
        static bool reported;
        static int sceneRevision;
        public static string MailboxPath => DirectoryPath;

        static Connector()
        {
            EditorApplication.update += Tick;
            EditorApplication.quitting += Stop;
            AssemblyReloadEvents.beforeAssemblyReload += Stop;
            EditorApplication.hierarchyChanged += () => sceneRevision++;
            Undo.undoRedoPerformed += () => sceneRevision++;
            Undo.postprocessModifications += modifications => { sceneRevision++; return modifications; };
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
                sceneRevision = sceneRevision, prefabStage = UnityEditor.SceneManagement.PrefabStageUtility.GetCurrentPrefabStage() != null,
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
                    NoLinks(path);
                    if (new FileInfo(path).Length > 16384) continue;
                    var r = JsonUtility.FromJson<Request>(File.ReadAllText(path));
                    if (r == null || !Guid.TryParseExact(r.id, "D", out _) ||
                        Path.GetFileName(path) != r.id + ".request.json" || r.session != Session || r.token != Token) continue;
                    var output = Path.Combine(DirectoryPath, r.id + ".result.json");
                    if (File.Exists(output)) continue; // At most once in this Editor session.
                    if (++processed > 20) break;
                    var result = new Result { id = r.id, session = Session, token = Token, status = "failed" };
                    if (!DateTime.TryParse(r.expiresAt, null, System.Globalization.DateTimeStyles.RoundtripKind, out var deadline) || deadline.ToUniversalTime() < DateTime.UtcNow)
                        result.errorCode = "UNITY_REQUEST_EXPIRED";
                    else if (r.action == "ping") { result.status = "succeeded"; result.target = CurrentState(); }
                    else if (r.action == "import") ExecuteImport(r, result);
                    else if (r.action == "place") ExecutePlace(r, result);
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
        static void ExecuteImport(Request request, Result result)
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode || EditorApplication.isCompiling)
            { result.errorCode = "UNITY_EDITOR_BUSY"; return; }
            if (request.items == null || request.items.Length < 1 || request.items.Length > 20)
            { result.errorCode = "INVALID_PARAMS"; return; }
            var started = Path.Combine(DirectoryPath, request.id + ".started.json");
            if (File.Exists(started)) { result.errorCode = "UNITY_OPERATION_INTERRUPTED"; return; }
            WritePrivate(started, new Result { id = request.id, session = Session, status = "started" });
            var results = new System.Collections.Generic.List<ItemResult>();
            foreach (var item in request.items)
            {
                var value = new ItemResult { assetId = item.assetId, fileId = item.fileId, status = "failed" };
                try
                {
                    if (!Guid.TryParseExact(item.assetId, "D", out _) || !Guid.TryParseExact(item.fileId, "D", out _) ||
                        item.targetRelativePath != "Assets/AIAssetHub/" + item.fileId + ".png" || item.size < 1 || item.size > 16 * 1024 * 1024)
                        throw new InvalidDataException();
                    NoLinks(item.sourcePath);
                    var source = Path.GetFullPath(item.sourcePath);
                    if (source.StartsWith(Project + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException();
                    byte[] bytes;
                    using (var stream = new FileStream(source, FileMode.Open, FileAccess.Read, FileShare.Read))
                    {
                        if (stream.Length != item.size) throw new InvalidDataException();
                        bytes = new byte[(int)item.size]; int offset = 0;
                        while (offset < bytes.Length) { int count = stream.Read(bytes, offset, bytes.Length - offset); if (count == 0) throw new InvalidDataException(); offset += count; }
                    }
                    using (var hash = System.Security.Cryptography.SHA256.Create())
                        if (BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant() != item.sha256) throw new InvalidDataException();
                    byte[] signature = { 137, 80, 78, 71, 13, 10, 26, 10 };
                    if (bytes.Length < 24) throw new InvalidDataException();
                    for (int index = 0; index < signature.Length; index++) if (bytes[index] != signature[index]) throw new InvalidDataException();
                    var destination = Path.Combine(Project, item.targetRelativePath); NoLinks(destination); NoLinks(destination + ".meta");
                    if (File.Exists(destination) || File.Exists(destination + ".meta")) { value.errorCode = "UNITY_TARGET_CONFLICT"; throw new IOException(); }
                    Directory.CreateDirectory(Path.GetDirectoryName(destination)); NoLinks(destination);
                    using (var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                    { value.copied = true; value.assetPath = item.targetRelativePath; output.Write(bytes, 0, bytes.Length); }
                    AssetDatabase.ImportAsset(item.targetRelativePath, ImportAssetOptions.ForceSynchronousImport);
                    var importer = AssetImporter.GetAtPath(item.targetRelativePath) as TextureImporter;
                    if (importer == null) throw new InvalidDataException();
                    importer.textureType = TextureImporterType.Sprite; importer.spriteImportMode = SpriteImportMode.Single;
                    importer.SaveAndReimport();
                    if (AssetDatabase.LoadAssetAtPath<Sprite>(item.targetRelativePath) == null) throw new InvalidDataException();
                    value.guid = AssetDatabase.AssetPathToGUID(item.targetRelativePath);
                    if (string.IsNullOrEmpty(value.guid)) throw new InvalidDataException();
                    value.status = "succeeded";
                }
                catch (Exception) { value.errorCode = value.errorCode ?? "UNITY_IMPORT_FAILED"; }
                results.Add(value);
            }
            result.items = results.ToArray();
            int successes = results.FindAll(i => i.status == "succeeded").Count;
            result.status = successes == results.Count ? "succeeded" : successes == 0 ? "failed" : "partial";
        }
        static bool ValidVector(float[] value, float bound, bool scale = false)
        {
            if (value == null || value.Length != 3) return false;
            foreach (var x in value) if (float.IsNaN(x) || float.IsInfinity(x) || Math.Abs(x) > bound || (scale && Math.Abs(x) < .0001f)) return false;
            return true;
        }
        static Vector3 Vector(float[] value) => new Vector3(value[0], value[1], value[2]);
        static void ExecutePlace(Request request, Result result)
        {
            var scene = SceneManager.GetActiveScene();
            if (EditorApplication.isPlayingOrWillChangePlaymode || EditorApplication.isCompiling ||
                UnityEditor.SceneManagement.PrefabStageUtility.GetCurrentPrefabStage() != null)
            { result.errorCode = "UNITY_EDITOR_BUSY"; return; }
            if (!scene.IsValid() || !scene.isLoaded || scene.path != request.scene || scene.handle.ToString() != request.sceneHandle || sceneRevision != request.sceneRevision)
            { result.errorCode = "UNITY_SCENE_CHANGED"; return; }
            if (request.items == null || request.items.Length < 1 || request.items.Length > 20 ||
                !ValidVector(request.position, 100000) || !ValidVector(request.rotation, 360000) || !ValidVector(request.scale, 1000, true) ||
                string.IsNullOrWhiteSpace(request.name) || request.name.Length > 80)
            { result.errorCode = "INVALID_PARAMS"; return; }
            var started = Path.Combine(DirectoryPath, request.id + ".started.json");
            if (File.Exists(started)) { result.errorCode = "UNITY_OPERATION_INTERRUPTED"; return; }
            WritePrivate(started, new Result { id = request.id, session = Session, status = "started" });
            var results = new System.Collections.Generic.List<ItemResult>();
            Undo.IncrementCurrentGroup(); int group = Undo.GetCurrentGroup(); Undo.SetCurrentGroupName("AI Asset Hub Sprite placement");
            foreach (var item in request.items)
            {
                var value = new ItemResult { assetId = item.assetId, fileId = item.fileId, status = "failed" };
                GameObject go = null;
                try
                {
                    if (!Guid.TryParseExact(item.fileId, "D", out _) || item.targetRelativePath != "Assets/AIAssetHub/" + item.fileId + ".png") throw new InvalidDataException();
                    var destination = Path.Combine(Project, item.targetRelativePath); NoLinks(destination); NoLinks(destination + ".meta");
                    if (AssetDatabase.AssetPathToGUID(item.targetRelativePath) != item.guid) throw new InvalidDataException();
                    using (var hash = System.Security.Cryptography.SHA256.Create())
                    using (var source = new FileStream(destination, FileMode.Open, FileAccess.Read, FileShare.Read))
                    {
                        if (source.Length > 16 * 1024 * 1024 || BitConverter.ToString(hash.ComputeHash(source)).Replace("-", "").ToLowerInvariant() != item.sha256) throw new InvalidDataException();
                    }
                    var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(item.targetRelativePath);
                    if (sprite == null) throw new InvalidDataException();
                    go = new GameObject(request.name); SceneManager.MoveGameObjectToScene(go, scene);
                    Undo.RegisterCreatedObjectUndo(go, "AI Asset Hub Sprite");
                    var renderer = Undo.AddComponent<SpriteRenderer>(go); renderer.sprite = sprite;
                    go.transform.position = Vector(request.position); go.transform.eulerAngles = Vector(request.rotation); go.transform.localScale = Vector(request.scale);
                    UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(scene);
                    if (EditorUtility.EntityIdToObject(go.GetEntityId()) != go || renderer.sprite != sprite) throw new InvalidDataException();
                    value.assetPath = item.targetRelativePath; value.guid = item.guid; value.entityId = EntityId.ToULong(go.GetEntityId()).ToString(System.Globalization.CultureInfo.InvariantCulture);
                    value.objectId = "session:" + Session + ":entity:" + value.entityId;
                    value.objectName = go.name; value.scene = scene.path; value.sceneHandle = scene.handle.ToString();
                    value.position = new[] { go.transform.position.x, go.transform.position.y, go.transform.position.z };
                    value.rotation = new[] { go.transform.eulerAngles.x, go.transform.eulerAngles.y, go.transform.eulerAngles.z };
                    value.scale = new[] { go.transform.localScale.x, go.transform.localScale.y, go.transform.localScale.z };
                    value.sceneDirty = scene.isDirty; value.sceneSaved = false; value.status = "succeeded";
                }
                catch (Exception)
                {
                    if (go != null) Undo.DestroyObjectImmediate(go);
                    value.errorCode = "UNITY_PLACE_FAILED";
                }
                results.Add(value);
            }
            Undo.CollapseUndoOperations(group); result.items = results.ToArray();
            int successes = results.FindAll(i => i.status == "succeeded").Count;
            result.status = successes == results.Count ? "succeeded" : successes == 0 ? "failed" : "partial";
        }
        static void Stop()
        {
            try { var path = Path.Combine(DirectoryPath, "connector.json"); NoLinks(path); if (File.Exists(path)) File.Delete(path); }
            catch (Exception) { }
        }
    }
}
