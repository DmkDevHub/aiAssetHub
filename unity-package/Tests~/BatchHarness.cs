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
            if (File.Exists(Path.Combine(root, "finish.test"))) EditorApplication.Exit(0);
            if (EditorApplication.timeSinceStartup > deadline) EditorApplication.Exit(2);
        }
    }
}
