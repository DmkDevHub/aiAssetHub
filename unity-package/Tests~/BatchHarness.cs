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
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            deadline = EditorApplication.timeSinceStartup + 240;
            EditorApplication.update += Wait;
            Connector.Tick();
        }
        static void Wait()
        {
            var root = Path.GetFullPath(Path.Combine(UnityEngine.Application.dataPath, ".."));
            if (File.Exists(Path.Combine(root, "finish.test")))
            {
                if (File.Exists(Path.Combine(root, "expect-placement.test")))
                {
                    var objects = UnityEngine.Object.FindObjectsByType<UnityEngine.SpriteRenderer>(UnityEngine.FindObjectsSortMode.None);
                    if (objects.Length != 1 || objects[0].sprite == null || objects[0].transform.position != new UnityEngine.Vector3(2, 3, 0) ||
                        !UnityEngine.SceneManagement.SceneManager.GetActiveScene().isDirty) { EditorApplication.Exit(3); return; }
                    Undo.PerformUndo();
                    if (UnityEngine.Object.FindObjectsByType<UnityEngine.SpriteRenderer>(UnityEngine.FindObjectsSortMode.None).Length != 0) { EditorApplication.Exit(4); return; }
                    File.WriteAllText(Path.Combine(root, "editor-assertions.json"), "{\"spriteVerified\":true,\"positionVerified\":true,\"undoVerified\":true,\"sceneAutoSaved\":false}");
                }
                EditorApplication.Exit(0);
            }
            if (EditorApplication.timeSinceStartup > deadline) EditorApplication.Exit(2);
        }
    }
}
