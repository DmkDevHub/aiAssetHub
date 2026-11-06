using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;

namespace AIAssetHub.Editor
{
    // Copied into an owned temporary project's Editor folder by verify-unity.py only.
    public static class BatchHarness
    {
        static double deadline;
        public static void Run()
        {
            var root = Path.GetFullPath(Path.Combine(UnityEngine.Application.dataPath, ".."));
            var unsafePath = Path.Combine(root, "unsafe-path.test");
            if (File.Exists(unsafePath))
            {
                bool rejected = false;
                try { Connector.NoLinks(File.ReadAllText(unsafePath)); } catch (IOException) { rejected = true; }
                if (!rejected) { EditorApplication.Exit(5); return; }
                File.WriteAllText(Path.Combine(root, "path-assertions.json"), "{\"danglingJunctionRejected\":true}");
            }
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            deadline = EditorApplication.timeSinceStartup + 240;
            EditorApplication.update += Wait;
            EditorApplication.update -= Connector.Tick;
            Connector.Tick();
        }
        static void Wait()
        {
            var root = Path.GetFullPath(Path.Combine(UnityEngine.Application.dataPath, ".."));
            // Pause is test-harness-only and never checked by production Connector code.
            if (File.Exists(Path.Combine(root, "pause.test"))) File.WriteAllText(Path.Combine(root, "paused.test"), "paused");
            else { if (File.Exists(Path.Combine(root, "paused.test"))) File.Delete(Path.Combine(root, "paused.test")); Connector.Tick(); }
            if (File.Exists(Path.Combine(root, "finish.test")))
            {
                if (File.Exists(Path.Combine(root, "expect-placement.test")))
                {
                    var objects = UnityEngine.Object.FindObjectsByType<UnityEngine.SpriteRenderer>(UnityEngine.FindObjectsSortMode.None);
                    if (objects.Length != 1 || objects[0].sprite == null || objects[0].transform.position != new UnityEngine.Vector3(2, 3, 0) ||
                        objects[0].transform.localScale != new UnityEngine.Vector3(2, 2, 1) ||
                        UnityEngine.Quaternion.Angle(objects[0].transform.rotation, UnityEngine.Quaternion.Euler(0, 0, 30)) > .01f ||
                        !UnityEngine.SceneManagement.SceneManager.GetActiveScene().isDirty) { EditorApplication.Exit(3); return; }
                    Undo.PerformUndo();
                    if (UnityEngine.Object.FindObjectsByType<UnityEngine.SpriteRenderer>(UnityEngine.FindObjectsSortMode.None).Length != 0) { EditorApplication.Exit(4); return; }
                    File.WriteAllText(Path.Combine(root, "editor-assertions.json"), "{\"spriteVerified\":true,\"positionVerified\":true,\"rotationScaleVerified\":true,\"undoVerified\":true,\"sceneAutoSaved\":false}");
                }
                EditorApplication.Exit(0);
            }
            if (EditorApplication.timeSinceStartup > deadline) EditorApplication.Exit(2);
        }
    }
}
