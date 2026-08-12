"use client";

import { useMutation } from "@apollo/client";

import { TagChip, TagInput, type Tag } from "@/components/tag-input";
import {
  ADD_PATIENT_TAGS,
  REMOVE_PATIENT_TAG,
  TAG_SUGGESTIONS,
} from "@/lib/graphql/operations";

type TagsResult = { tags: Tag[] };

/**
 * The tags section on a patient profile. Everyone sees the chips; ADMIN and
 * NURSE can add (with typeahead) and remove them.
 */
export function PatientTagsPanel({
  patientId,
  tags,
  canEdit,
}: {
  patientId: string;
  tags: Tag[];
  canEdit: boolean;
}) {
  const refetch = [{ query: TAG_SUGGESTIONS, variables: { query: null } }];

  const [addTags, { loading: adding, error: addError }] = useMutation<{
    addPatientTags: TagsResult;
  }>(ADD_PATIENT_TAGS, { refetchQueries: refetch });

  const [removeTag, { error: removeError }] = useMutation<{
    removePatientTag: TagsResult;
  }>(REMOVE_PATIENT_TAG, { refetchQueries: refetch });

  const error = addError ?? removeError;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">Tags</span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {tags.length === 0 ? (
          <span className="text-sm text-muted-foreground">No tags yet</span>
        ) : (
          tags.map((t) => (
            <TagChip
              key={t.id ?? t.label}
              label={t.label}
              category={t.category}
              onRemove={
                canEdit
                  ? () =>
                      removeTag({
                        variables: { patientId, tag: t.label },
                      })
                  : undefined
              }
            />
          ))
        )}
      </div>

      {canEdit ? (
        <div className="pt-1">
          <TagInput
            exclude={tags.map((t) => t.label)}
            placeholder={adding ? "Adding…" : "Add a tag…"}
            onSelect={(label) =>
              addTags({ variables: { patientId, tags: [label] } })
            }
          />
        </div>
      ) : null}

      {error ? <p className="text-sm text-red-600">{error.message}</p> : null}
    </div>
  );
}
